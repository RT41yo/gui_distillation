from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    method: str
    error: str | None = None
    click_point: tuple[int, int] | None = None
    activated: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "method": self.method,
            "error": self.error,
            "click_point": list(self.click_point) if self.click_point else None,
            "activated": self.activated,
        }


class ActionExecutor:
    """Execute one UI action. MVP supports bbox center click only."""

    def __init__(self, display: str, window_name: str | None = None) -> None:
        self.display = display
        self.window_name = window_name
        os.environ["DISPLAY"] = display

    def activate_window(self) -> bool:
        if not self.window_name:
            return False

        try:
            subprocess.run(
                [
                    "xdotool",
                    "search",
                    "--name",
                    self.window_name,
                    "windowactivate",
                    "--sync",
                    "windowfocus",
                    "--sync",
                ],
                capture_output=True,
                timeout=3,
                env={**os.environ, "DISPLAY": self.display},
                check=False,
            )
            time.sleep(0.15)
            return True
        except Exception:
            return False

    def click_bbox(self, bbox: list[int] | tuple[int, int, int, int]) -> ExecutionResult:
        activated = self.activate_window()

        try:
            import pyautogui
        except Exception as exc:
            return ExecutionResult(
                ok=False,
                method="bbox_click",
                error=f"pyautogui import failed: {exc}",
                activated=activated,
            )

        try:
            x, y, w, h = [int(v) for v in bbox]
            if x < 0 or y < 0 or w <= 1 or h <= 1:
                return ExecutionResult(
                    ok=False,
                    method="bbox_click",
                    error=f"invalid bbox: {bbox}",
                    activated=activated,
                )

            cx = x + w // 2
            cy = y + h // 2

            pyautogui.click(cx, cy)
            time.sleep(0.25)

            return ExecutionResult(
                ok=True,
                method="bbox_click",
                click_point=(cx, cy),
                activated=activated,
            )
        except Exception as exc:
            return ExecutionResult(
                ok=False,
                method="bbox_click",
                error=str(exc),
                activated=activated,
            )
