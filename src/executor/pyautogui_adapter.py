"""
PyAutoGUI adapter — handles app lifecycle and low-level GUI interactions.

Wraps subprocess management and pyautogui calls. Does NOT make decisions;
only executes what it is told.
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import pyautogui

logger = logging.getLogger(__name__)


class PyAutoGUIAdapter:
    """
    Manages application lifecycle and dispatches GUI actions via pyautogui.

    Unlike GUIAutomation (Phase 1), this adapter:
      - Accepts multi-word launchers (e.g. "libreoffice --writer")
      - Has no dependency on app_config / button YAML
      - Does not produce Phase-1 step artifacts
    """

    def __init__(self, display: str = ":99", action_delay: float = 0.5) -> None:
        self._display = display
        self._action_delay = action_delay
        self._process: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
        os.environ["DISPLAY"] = display
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.1

    # ------------------------------------------------------------------
    # App lifecycle
    # ------------------------------------------------------------------

    def launch(self, launcher: str, startup_wait: float = 3.0) -> None:
        """Launch the application given its full launcher string."""
        args = shlex.split(launcher)
        logger.info("Launching: %s", args)
        self._process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
        )
        time.sleep(startup_wait)
        if self._process.poll() is not None:
            raise RuntimeError(f"Launcher '{launcher}' exited immediately after start")
        logger.info("App launched (PID=%s)", self._process.pid)

    def close(self, graceful_timeout: float = 5.0) -> None:
        """Terminate the application."""
        if self._process is None:
            return
        self._process.terminate()
        deadline = time.monotonic() + graceful_timeout
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                logger.info("App closed gracefully")
                self._process = None
                return
            time.sleep(0.2)
        logger.warning("App did not exit gracefully — killing")
        self._process.kill()
        self._process.wait(timeout=3.0)
        self._process = None

    # ------------------------------------------------------------------
    # GUI actions
    # ------------------------------------------------------------------

    def click(self, x: float, y: float, button: str = "left") -> None:
        """Click at absolute pixel coordinates."""
        pyautogui.click(int(x), int(y), button=button)
        time.sleep(self._action_delay)

    def type_text(self, text: str, interval: float = 0.05) -> None:
        """Type a string character by character."""
        pyautogui.write(text, interval=interval)
        time.sleep(self._action_delay)

    def hotkey(self, keys: List[str]) -> None:
        """Press a key combination, e.g. ['ctrl', 's']."""
        pyautogui.hotkey(*keys)
        time.sleep(self._action_delay)

    def scroll(self, x: float, y: float, direction: str = "down", amount: int = 3) -> None:
        """Scroll at coordinates."""
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks, x=int(x), y=int(y))
        time.sleep(self._action_delay)

    def wait(self, duration: float = 1.0) -> None:
        """Pause execution."""
        time.sleep(duration)
