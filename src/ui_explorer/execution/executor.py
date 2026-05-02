from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    method: str
    error: str | None = None
    click_point: tuple[int, int] | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "method": self.method,
            "error": self.error,
            "click_point": list(self.click_point) if self.click_point else None,
        }


class ActionExecutor:
    """Execute one UI action. MVP supports bbox center click only."""

    def __init__(self, display: str) -> None:
        self.display = display
        os.environ["DISPLAY"] = display

    def click_bbox(self, bbox: list[int] | tuple[int, int, int, int]) -> ExecutionResult:
        try:
            import pyautogui
        except Exception as exc:
            return ExecutionResult(ok=False, method="bbox_click", error=f"pyautogui import failed: {exc}")

        try:
            x, y, w, h = [int(v) for v in bbox]
            if x < 0 or y < 0 or w <= 1 or h <= 1:
                return ExecutionResult(ok=False, method="bbox_click", error=f"invalid bbox: {bbox}")

            cx = x + w // 2
            cy = y + h // 2

            pyautogui.click(cx, cy)
            time.sleep(0.25)

            return ExecutionResult(ok=True, method="bbox_click", click_point=(cx, cy))
        except Exception as exc:
            return ExecutionResult(ok=False, method="bbox_click", error=str(exc))
