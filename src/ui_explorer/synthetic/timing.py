from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class StageTimer:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self.timings: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str, **context: Any) -> Iterator[None]:
        context_bits = " ".join(f"{key}={value}" for key, value in context.items())
        suffix = f" {context_bits}" if context_bits else ""
        self._logger.info("stage=%s status=start%s", name, suffix)
        started = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - started
            self.timings[name] = elapsed
            self._logger.info("stage=%s status=done elapsed=%.2fs%s", name, elapsed, suffix)

    def summary(self) -> dict[str, float]:
        return dict(self.timings)
