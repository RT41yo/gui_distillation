from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# USD per token (from OpenRouter pricing table, fetched 2026-06-06).
FALLBACK_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o-mini": {"prompt": 0.00000015, "completion": 0.0000006},
    "gpt-4o-mini-2024-07-18": {"prompt": 0.00000015, "completion": 0.0000006},
    "gpt-4o": {"prompt": 0.0000025, "completion": 0.00001},
    "gpt-4o-2024-08-06": {"prompt": 0.0000025, "completion": 0.00001},
}

_pricing_cache: dict[str, dict[str, float]] | None = None


@dataclass(frozen=True)
class UsageCost:
    num_tokens: int
    cost_usd: float
    cost_source: str
    prompt_tokens: int
    completion_tokens: int


def _normalize_model_id(model: str) -> str:
    return model.strip().lower()


def _model_lookup_keys(model: str) -> list[str]:
    normalized = _normalize_model_id(model)
    keys = [normalized]
    if "/" in normalized:
        keys.append(normalized.split("/", 1)[1])
    return keys


def fetch_openrouter_pricing(*, timeout: float = 15.0) -> dict[str, dict[str, float]]:
    global _pricing_cache
    if _pricing_cache is not None:
        return _pricing_cache

    pricing: dict[str, dict[str, float]] = dict(FALLBACK_MODEL_PRICING)

    try:
        req = request.Request(OPENROUTER_MODELS_URL, method="GET")
        with request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, json.JSONDecodeError, TimeoutError):
        _pricing_cache = pricing
        return pricing

    for entry in body.get("data", []):
        model_id = entry.get("id")
        raw_pricing = entry.get("pricing") or {}
        prompt = raw_pricing.get("prompt")
        completion = raw_pricing.get("completion")
        if not model_id or prompt is None or completion is None:
            continue

        rates = {
            "prompt": float(prompt),
            "completion": float(completion),
        }
        pricing[_normalize_model_id(model_id)] = rates
        if "/" in model_id:
            pricing[_normalize_model_id(model_id.split("/", 1)[1])] = rates

    _pricing_cache = pricing
    return pricing


def lookup_model_rates(model: str) -> dict[str, float]:
    pricing = fetch_openrouter_pricing()
    for key in _model_lookup_keys(model):
        rates = pricing.get(key)
        if rates is not None:
            return rates

    for key in _model_lookup_keys(model):
        for known, rates in pricing.items():
            if key in known or known in key:
                return rates

    raise KeyError(f"no pricing found for model: {model}")


def extract_api_cost_usd(response_body: dict[str, Any]) -> float | None:
    usage = response_body.get("usage") or {}
    for container in (usage, response_body):
        cost = container.get("cost")
        if cost is not None:
            return float(cost)
        total_cost = container.get("total_cost")
        if total_cost is not None:
            return float(total_cost)
    return None


def compute_usage_cost(
    *,
    response_body: dict[str, Any],
    model: str,
) -> UsageCost:
    usage = response_body.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    num_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))

    api_cost = extract_api_cost_usd(response_body)
    if api_cost is not None:
        return UsageCost(
            num_tokens=num_tokens,
            cost_usd=api_cost,
            cost_source="api",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    rates = lookup_model_rates(model)
    cost_usd = (prompt_tokens * rates["prompt"]) + (completion_tokens * rates["completion"])
    return UsageCost(
        num_tokens=num_tokens,
        cost_usd=cost_usd,
        cost_source="openrouter_pricing",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
