from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path


def save_screenshot(
    path: Path,
    *,
    display: str | None = None,
    overwrite: bool = False,
) -> bool:
    """
    Best-effort screenshot capture for the currently visible X display.

    This must never fail exploration. If screenshot capture fails, return False
    and keep graph/state generation working.
    """
    path = Path(path)

    if path.exists() and not overwrite:
        return True

    path.parent.mkdir(parents=True, exist_ok=True)

    old_display = os.environ.get("DISPLAY")
    if display:
        os.environ["DISPLAY"] = display

    try:
        # Primary path: pyautogui is already used by the project for GUI automation.
        try:
            import pyautogui

            image = pyautogui.screenshot()
            image.save(path)
            return True
        except Exception:
            logging.exception("pyautogui screenshot failed: %s", path)

        # Fallback path: ImageMagick import, if installed.
        if shutil.which("import"):
            result = subprocess.run(
                ["import", "-window", "root", str(path)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if result.returncode == 0 and path.exists():
                return True

            logging.warning(
                "ImageMagick import screenshot failed rc=%s stderr=%s",
                result.returncode,
                result.stderr.strip(),
            )

        return False

    except Exception:
        logging.exception("Failed to save screenshot: %s", path)
        return False

    finally:
        if display:
            if old_display is None:
                os.environ.pop("DISPLAY", None)
            else:
                os.environ["DISPLAY"] = old_display
