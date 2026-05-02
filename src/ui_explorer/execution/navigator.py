from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from ui_explorer.execution.wait import A11YWaiter, CapturedState


@dataclass(frozen=True)
class NavigationResult:
    ok: bool
    target_state: str
    actual_state: str | None
    attempts: int
    reason: str
    xml_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "target_state": self.target_state,
            "actual_state": self.actual_state,
            "attempts": self.attempts,
            "reason": self.reason,
            "xml_path": self.xml_path,
        }


class Navigator:
    """Navigation helpers. MVP supports reset-to-root via Escape."""

    def __init__(self, a11y_name: str, display: str) -> None:
        self.a11y_name = a11y_name
        self.display = display
        os.environ["DISPLAY"] = display

    def reset_to_root(
        self,
        root_state_id: str,
        output_dir: Path,
        max_escapes: int = 5,
        delay_s: float = 0.25,
    ) -> tuple[NavigationResult, CapturedState | None]:
        try:
            import pyautogui
        except Exception as exc:
            return (
                NavigationResult(
                    ok=False,
                    target_state=root_state_id,
                    actual_state=None,
                    attempts=0,
                    reason=f"pyautogui import failed: {exc}",
                ),
                None,
            )

        waiter = A11YWaiter(a11y_name=self.a11y_name)
        output_dir.mkdir(parents=True, exist_ok=True)

        last_state: CapturedState | None = None

        # Capture once before pressing Escape. We may already be at root.
        state = waiter.capture_once(output_dir / "reset_00.xml")
        if state.signature.state_id == root_state_id:
            return (
                NavigationResult(
                    ok=True,
                    target_state=root_state_id,
                    actual_state=state.signature.state_id,
                    attempts=0,
                    reason="already at root",
                    xml_path=str(state.xml_path),
                ),
                state,
            )

        last_state = state

        for attempt in range(1, max_escapes + 1):
            pyautogui.press("escape")
            time.sleep(delay_s)

            state = waiter.capture_once(output_dir / f"reset_{attempt:02d}.xml")
            last_state = state

            if state.signature.state_id == root_state_id:
                return (
                    NavigationResult(
                        ok=True,
                        target_state=root_state_id,
                        actual_state=state.signature.state_id,
                        attempts=attempt,
                        reason="root reached via Escape",
                        xml_path=str(state.xml_path),
                    ),
                    state,
                )

        return (
            NavigationResult(
                ok=False,
                target_state=root_state_id,
                actual_state=last_state.signature.state_id if last_state else None,
                attempts=max_escapes,
                reason="root not reached after Escape attempts",
                xml_path=str(last_state.xml_path) if last_state else None,
            ),
            last_state,
        )
