from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompletionParams:
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] = ()
    timeout: float | None = None

    def merge(self, overrides: CompletionParams) -> CompletionParams:
        return CompletionParams(
            temperature=(
                overrides.temperature
                if overrides.temperature is not None
                else self.temperature
            ),
            top_p=overrides.top_p if overrides.top_p is not None else self.top_p,
            max_tokens=(
                overrides.max_tokens
                if overrides.max_tokens is not None
                else self.max_tokens
            ),
            presence_penalty=(
                overrides.presence_penalty
                if overrides.presence_penalty is not None
                else self.presence_penalty
            ),
            frequency_penalty=(
                overrides.frequency_penalty
                if overrides.frequency_penalty is not None
                else self.frequency_penalty
            ),
            seed=overrides.seed if overrides.seed is not None else self.seed,
            stop=overrides.stop if overrides.stop else self.stop,
            timeout=overrides.timeout if overrides.timeout is not None else self.timeout,
        )

    def apply_to_payload(self, payload: dict[str, Any]) -> None:
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.presence_penalty is not None:
            payload["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty is not None:
            payload["frequency_penalty"] = self.frequency_penalty
        if self.seed is not None:
            payload["seed"] = self.seed
        if self.stop:
            payload["stop"] = list(self.stop)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        self.apply_to_payload(payload)
        if self.timeout is not None:
            payload["timeout"] = self.timeout
        return payload


CREATIVE_COMPLETION_PARAMS = CompletionParams(
    temperature=0.85,
    top_p=0.92,
    frequency_penalty=0.5,
    presence_penalty=0.3,
)


def add_completion_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("LLM sampling (omit any knob to use provider default)")
    group.add_argument(
        "--creative",
        action="store_true",
        help=(
            "Apply a mild creative preset (temperature=0.85, top_p=0.92, "
            "frequency_penalty=0.5, presence_penalty=0.3). Explicit knob flags override."
        ),
    )
    group.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature; higher values increase creativity.",
    )
    group.add_argument(
        "--top-p",
        type=float,
        default=None,
        help="Nucleus sampling top_p.",
    )
    group.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Maximum completion tokens.",
    )
    group.add_argument(
        "--presence-penalty",
        type=float,
        default=None,
        help=(
            "OpenAI presence_penalty (-2.0 to 2.0); discourages reusing topics already mentioned."
        ),
    )
    group.add_argument(
        "--frequency-penalty",
        type=float,
        default=None,
        help=(
            "OpenAI frequency_penalty (-2.0 to 2.0); penalizes repeated tokens (OpenAI's "
            "repetition control — there is no repetition_penalty parameter)."
        ),
    )
    group.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional deterministic sampling seed when supported.",
    )
    group.add_argument(
        "--stop",
        action="append",
        default=[],
        help="Stop sequence (repeatable).",
    )
    group.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="HTTP request timeout in seconds (default: 300).",
    )


def completion_params_from_args(args: argparse.Namespace) -> CompletionParams:
    preset = CREATIVE_COMPLETION_PARAMS if args.creative else CompletionParams()
    explicit = CompletionParams(
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        presence_penalty=args.presence_penalty,
        frequency_penalty=args.frequency_penalty,
        seed=args.seed,
        stop=tuple(args.stop),
        timeout=args.timeout,
    )
    return preset.merge(explicit)
