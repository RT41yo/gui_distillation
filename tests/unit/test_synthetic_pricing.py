from __future__ import annotations

from ui_explorer.synthetic.pricing import (
    compute_usage_cost,
    extract_api_cost_usd,
    lookup_model_rates,
)


def test_extract_api_cost_from_usage() -> None:
    body = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.0012}}
    assert extract_api_cost_usd(body) == 0.0012


def test_extract_api_cost_missing() -> None:
    body = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    assert extract_api_cost_usd(body) is None


def test_compute_usage_cost_from_openrouter_pricing() -> None:
    body = {
        "model": "gpt-4o-mini-2024-07-18",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
    }
    result = compute_usage_cost(response_body=body, model="gpt-4o-mini-2024-07-18")
    assert result.num_tokens == 1500
    assert result.cost_source == "openrouter_pricing"
    assert abs(result.cost_usd - ((1000 * 0.00000015) + (500 * 0.0000006))) < 1e-12


def test_compute_usage_cost_prefers_api_cost() -> None:
    body = {
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
            "cost": 0.42,
        }
    }
    result = compute_usage_cost(response_body=body, model="gpt-4o-mini")
    assert result.cost_usd == 0.42
    assert result.cost_source == "api"


def test_lookup_model_rates_known_model() -> None:
    rates = lookup_model_rates("gpt-4o-mini")
    assert rates["prompt"] == 0.00000015
    assert rates["completion"] == 0.0000006
