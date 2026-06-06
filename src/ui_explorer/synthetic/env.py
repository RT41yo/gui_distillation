from __future__ import annotations

import os
from pathlib import Path

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def resolve_openai_config(*, env_path: Path, model_override: str | None) -> dict[str, str]:
    load_env_file(env_path)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            f"OPENAI_API_KEY is not set. Add it to {env_path} or export it in the shell."
        )

    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip().rstrip("/")
    model = (model_override or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }
