from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from ui_explorer.synthetic.pricing import UsageCost, compute_usage_cost


@dataclass(frozen=True)
class StructuredCompletionResult:
    content: dict[str, Any]
    usage_cost: UsageCost
    model: str
    raw_response: dict[str, Any]


def _image_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "application/octet-stream"


def build_openai_messages(prompt_text: str, screenshot_path: str | None) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt_text}]

    if screenshot_path:
        path = Path(screenshot_path)
        if path.exists():
            encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
            mime_type = _image_mime_type(path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
            })

    return [{"role": "user", "content": content}]


def openai_structured_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    json_schema: dict[str, Any],
    timeout: float = 300.0,
) -> StructuredCompletionResult:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {
            "type": "json_schema",
            "json_schema": json_schema,
        },
    }

    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected OpenAI API response shape: {body}") from exc

    if isinstance(content, dict):
        parsed = content
    else:
        parsed = json.loads(content)

    response_model = str(body.get("model") or model)
    usage_cost = compute_usage_cost(response_body=body, model=response_model)

    return StructuredCompletionResult(
        content=parsed,
        usage_cost=usage_cost,
        model=response_model,
        raw_response=body,
    )
