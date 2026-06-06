from __future__ import annotations

import base64
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from ui_explorer.synthetic.llm_args import CompletionParams
from ui_explorer.synthetic.pricing import UsageCost, compute_usage_cost

log = logging.getLogger(__name__)


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
            log.info("Attached screenshot %s (%d bytes)", path, path.stat().st_size)
        else:
            log.warning("Screenshot path missing, continuing without image: %s", path)

    return [{"role": "user", "content": content}]


def _post_chat_completion(req: request.Request, request_timeout: float) -> dict[str, Any]:
    with request.urlopen(req, timeout=request_timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_for_response_with_countdown(
    future: Any,
    *,
    started: float,
    request_timeout: float,
) -> dict[str, Any]:
    next_log_at = started
    while True:
        now = time.monotonic()
        elapsed = now - started
        remaining = max(0.0, request_timeout - elapsed)
        sys.stderr.write(
            f"\rWaiting for API response... {remaining:4.0f}s remaining "
            f"({elapsed:4.0f}s elapsed / {request_timeout:.0f}s timeout)   "
        )
        sys.stderr.flush()

        if now >= next_log_at:
            log.info(
                "Waiting for API response... %.0fs remaining (%.0fs elapsed / %.0fs timeout)",
                remaining,
                elapsed,
                request_timeout,
            )
            next_log_at = now + 5.0

        if future.done():
            sys.stderr.write("\n")
            sys.stderr.flush()
            return future.result()

        try:
            return future.result(timeout=1.0)
        except FuturesTimeoutError:
            continue


def openai_structured_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    json_schema: dict[str, Any],
    completion_params: CompletionParams | None = None,
    timeout: float = 300.0,
) -> StructuredCompletionResult:
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": json_schema,
        },
    }
    request_timeout = timeout
    if completion_params is not None:
        completion_params.apply_to_payload(payload)
        if completion_params.timeout is not None:
            request_timeout = completion_params.timeout

    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    schema_name = json_schema.get("name", "unknown")
    request_params = {
        key: value
        for key, value in payload.items()
        if key not in {"messages", "response_format"}
    }
    log.info(
        "Calling chat/completions model=%s schema=%s timeout=%.0fs params=%s",
        model,
        schema_name,
        request_timeout,
        request_params,
    )
    started = time.monotonic()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_post_chat_completion, req, request_timeout)
            body = _wait_for_response_with_countdown(
                future,
                started=started,
                request_timeout=request_timeout,
            )
    except error.HTTPError as exc:
        elapsed = time.monotonic() - started
        detail = exc.read().decode("utf-8", errors="replace")
        log.error("API HTTP %s after %.1fs: %s", exc.code, elapsed, detail)
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        elapsed = time.monotonic() - started
        log.error("API request failed after %.1fs: %s", elapsed, exc)
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc

    elapsed = time.monotonic() - started

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
    log.info(
        "API completed in %.1fs model=%s tokens=%d cost=$%.6f (%s)",
        elapsed,
        response_model,
        usage_cost.num_tokens,
        usage_cost.cost_usd,
        usage_cost.cost_source,
    )

    return StructuredCompletionResult(
        content=parsed,
        usage_cost=usage_cost,
        model=response_model,
        raw_response=body,
    )
