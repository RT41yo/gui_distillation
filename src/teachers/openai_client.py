from __future__ import annotations

import base64
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None

from openai import (  # type: ignore
    OpenAI,
    AuthenticationError,
    BadRequestError,
    PermissionDeniedError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# Errors that indicate a permanent failure — retrying will not help.
_NON_RETRYABLE = (AuthenticationError, BadRequestError, PermissionDeniedError)


JsonDict = Dict[str, Any]


class SettingsLoader:
    """Load config/settings.yaml with deep-merged overrides[runtime.profile]."""

    @staticmethod
    def load(path: str | Path) -> JsonDict:
        p = Path(path)
        if not p.exists():
            return {}
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        profile = SettingsLoader.get(data, "runtime.profile", None)
        overrides = SettingsLoader.get(data, "overrides", {})
        if profile and isinstance(overrides, dict) and profile in overrides:
            base = dict(data)
            return SettingsLoader.deep_merge(base, overrides[profile])
        return data

    @staticmethod
    def deep_merge(base: JsonDict, override: JsonDict) -> JsonDict:
        """Deep-merge override into base (dicts only). Does not mutate inputs."""
        result = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = SettingsLoader.deep_merge(result[k], v)  # type: ignore[arg-type]
            else:
                result[k] = v
        return result

    @staticmethod
    def get(dct: JsonDict, dotted_path: str, default: Any) -> Any:
        cur: Any = dct
        for part in dotted_path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


@dataclass
class TeacherRawResponse:
    text: str
    model: str
    latency_s: float
    request_id: Optional[str] = None
    usage: Optional[JsonDict] = None


class OpenAIAnnotatorClient:
    """
    OpenAI client for multimodal prompts (text + images) via Responses API.

    Uses:
      - teacher.api.timeout / max_retries / retry_delay from settings.yaml
      - model/temperature/max_tokens from teacher config YAML (preferred)
        with fallback to settings.teacher.available entry.
    """

    def __init__(
        self,
        settings_path: str = "config/settings.yaml",
        teacher_config_path: str = "config/teachers/openai_gpt.yaml",
        dotenv_path: str = ".env",
        api_key_env: str = "OPENAI_API_KEY",
    ) -> None:
        self.settings = SettingsLoader.load(settings_path)
        self.teacher_cfg = self._load_yaml(Path(teacher_config_path))

        # Load .env (user said they created it)
        if load_dotenv is not None:
            load_dotenv(dotenv_path)

        api_key = os.getenv(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"OpenAI API key not found. Expected env var {api_key_env}. "
                f"Put it in {dotenv_path} as {api_key_env}=... or export it."
            )

        # Settings-based defaults
        timeout_s = float(SettingsLoader.get(self.settings, "teacher.api.timeout", 30))
        retries = int(SettingsLoader.get(self.settings, "teacher.api.max_retries", 3))
        retry_delay = float(SettingsLoader.get(self.settings, "teacher.api.retry_delay", 2))

        self.timeout_s = float(self.teacher_cfg.get("timeout_s", timeout_s))
        self.retries = int(self.teacher_cfg.get("retries", retries))
        self.retry_delay_s = float(self.teacher_cfg.get("retry_delay_s", retry_delay))

        # Model defaults:
        # Prefer teacher config yaml; fallback to settings.teacher.available where name == settings.teacher.default
        default_teacher_name = str(SettingsLoader.get(self.settings, "teacher.default", "gpt-4v"))
        avail = SettingsLoader.get(self.settings, "teacher.available", [])
        fallback_max_tokens = 1000
        fallback_temperature = 0.0
        if isinstance(avail, list):
            for item in avail:
                if isinstance(item, dict) and item.get("name") == default_teacher_name:
                    fallback_max_tokens = int(item.get("max_tokens", fallback_max_tokens))
                    fallback_temperature = float(item.get("temperature", fallback_temperature))

        self.model = str(self.teacher_cfg.get("model", self.teacher_cfg.get("name", default_teacher_name)))
        self.temperature = float(self.teacher_cfg.get("temperature", fallback_temperature))
        self.max_output_tokens = int(self.teacher_cfg.get("max_output_tokens", fallback_max_tokens))

        # Image detail (OpenAI supports low/high/auto for some models)
        self.image_detail = str(self.teacher_cfg.get("image_detail", "auto"))

        # Optional base_url via teacher config
        base_url = self.teacher_cfg.get("base_url") or os.getenv("OPENAI_BASE_URL")
        self.client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    @staticmethod
    def _load_yaml(path: Path) -> JsonDict:
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    @staticmethod
    def _image_to_data_url(image_path: Path) -> str:
        ext = image_path.suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        if ext not in {"png", "jpeg", "webp"}:
            ext = "png"
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/{ext};base64,{b64}"

    def infer(
        self,
        prompt_text: str,
        image_paths: Optional[List[Path]] = None,
        prefer_json: bool = True,
    ) -> TeacherRawResponse:
        """
        Returns raw text. We *request* JSON when prefer_json=True, but still parse robustly later.
        """
        image_paths = image_paths or []

        content: List[JsonDict] = [{"type": "input_text", "text": prompt_text}]
        for p in image_paths:
            content.append(
                {
                    "type": "input_image",
                    "image_url": self._image_to_data_url(p),
                    "detail": self.image_detail,
                }
            )

        text_cfg = {"format": {"type": "json_object"}} if prefer_json else None

        last_err: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self.client.responses.create(
                    model=self.model,
                    input=[{"role": "user", "content": content}],
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                    text=text_cfg,
                    timeout=self.timeout_s,
                )
                latency = time.perf_counter() - t0

                # robust text extraction
                out_text = ""
                if hasattr(resp, "output_text") and getattr(resp, "output_text"):
                    out_text = resp.output_text  # type: ignore[attr-defined]
                else:
                    for item in getattr(resp, "output", []) or []:
                        for c in getattr(item, "content", []) or []:
                            if getattr(c, "type", None) == "output_text":
                                out_text += getattr(c, "text", "")

                usage = getattr(resp, "usage", None)
                usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else usage
                return TeacherRawResponse(
                    text=str(out_text).strip(),
                    model=self.model,
                    latency_s=latency,
                    request_id=getattr(resp, "id", None),
                    usage=usage_dict,
                )
            except _NON_RETRYABLE:
                raise
            except Exception as e:
                last_err = e
                if attempt < self.retries:
                    delay = self.retry_delay_s * (2 ** (attempt - 1))
                    if isinstance(e, RateLimitError):
                        retry_after = _parse_retry_after(e)
                        if retry_after is not None:
                            delay = retry_after
                    logger.warning(
                        "OpenAI request attempt %d/%d failed (%s: %s); retrying in %.1fs",
                        attempt, self.retries, type(e).__name__, e, delay,
                    )
                    time.sleep(delay)
                else:
                    break

        raise RuntimeError(f"OpenAI request failed after {self.retries} attempts: {last_err}") from last_err


def _parse_retry_after(exc: Exception) -> Optional[float]:
    """Extract the Retry-After value (seconds) from a RateLimitError response header, if present."""
    try:
        headers = getattr(getattr(exc, "response", None), "headers", None) or {}
        value = headers.get("retry-after") or headers.get("Retry-After")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
