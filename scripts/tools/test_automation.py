#!/usr/bin/env python3
# scripts/tools/test_automation.py
"""
Test script for GUI automation infrastructure (Phase 0.3).

This script verifies that:
1) DISPLAY is set and X11 screen is accessible
2) GUIAutomation can be constructed
3) Target application can be launched
4) Screenshots can be taken and saved
5) A simple click can be executed
6) A "step" produces before/after artifacts (if supported by GUIAutomation)
7) Application can be closed
8) Optional: click a calibrated calculator button (digit_5) if coordinates are available

Important design note:
- This script is intentionally tolerant to partially implemented GUIAutomation.
  It will SKIP tests if a method is not available yet.

Run:
  cd /mnt/repo
  python scripts/tools/test_automation.py --display :99 --app gnome-calculator -v
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, Tuple

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.core.automation import GUIAutomation  # noqa: E402
from src.core.exceptions import (  # noqa: E402
    AppLaunchError,
    DisplayNotFoundError,
    ScreenshotError,
    GUIDistillationError,
)


LOGGER = logging.getLogger("test_automation")


class AutomationTester:
    """
    Test suite for GUI automation.
    Runs a series of checks to verify infrastructure is working.
    """

    def __init__(self, app_name: str = "gnome-calculator", display: str = ":99"):
        self.app_name = app_name
        self.display = display

        self.automation: Optional[GUIAutomation] = None  # type: ignore[type-arg]
        self.test_passed = 0
        self.test_failed = 0
        self.test_skipped = 0

        self.output_dir = REPO_ROOT / "data" / "test_automation"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def print_header(self, text: str) -> None:
        print("\n" + "=" * 70)
        print(f" {text}")
        print("=" * 70)

    def print_result(self, test_name: str, success: bool, message: str = "") -> None:
        if success:
            print(f"  ✅ {test_name}: {message}" if message else f"  ✅ {test_name}")
            self.test_passed += 1
        else:
            print(f"  ❌ {test_name}: {message}" if message else f"  ❌ {test_name}")
            self.test_failed += 1

    def print_skipped(self, test_name: str, reason: str) -> None:
        print(f"  ⏭️  {test_name}: {reason}")
        self.test_skipped += 1

    def print_summary(self) -> None:
        print("\n" + "=" * 70)
        print(" TEST SUMMARY")
        print("=" * 70)
        print(f"  ✅ Passed:  {self.test_passed}")
        print(f"  ❌ Failed:  {self.test_failed}")
        print(f"  ⏭️  Skipped: {self.test_skipped}")

        if self.test_failed == 0:
            print("\n  🎉 ALL TESTS PASSED (or skipped appropriately).")
        else:
            print("\n  ⚠️  Some tests failed. See details above.")

    def run_all_tests(self) -> None:
        self.print_header("GUI AUTOMATION TEST SUITE (Phase 0.3)")
        print(f"Repo:    {REPO_ROOT}")
        print(f"App:     {self.app_name}")
        print(f"Display: {self.display}")
        print(f"Outdir:  {self.output_dir}")

        self._ensure_display_env()

        self.test_display()
        self.test_automation_init()
        self.test_launch_app()
        self.test_screenshot()
        self.test_click()
        self.test_before_after_step()
        self.test_close_app()
        self.test_calculator_digit_5_optional()

        self.print_summary()

    # ----------------------------
    # Helpers
    # ----------------------------
    def _ensure_display_env(self) -> None:
        """
        Ensure DISPLAY is set for the current process.
        We set it early so that pyautogui uses the intended display.
        """
        os.environ["DISPLAY"] = self.display

    def _require_automation(self, test_name: str) -> bool:
        if self.automation is None:
            self.print_skipped(test_name, "No automation instance")
            return False
        return True

    def _safe_import_pyautogui(self) -> Any:
        try:
            import pyautogui  # type: ignore

            return pyautogui
        except Exception as e:
            raise RuntimeError(
                f"Cannot import/use pyautogui: {e}. "
                "Ensure dependencies installed and X11 DISPLAY is reachable."
            ) from e

    # ----------------------------
    # Tests
    # ----------------------------
    def test_display(self) -> None:
        """Test if display is accessible and screen size can be read."""
        pyautogui = self._safe_import_pyautogui()
        try:
            display = os.environ.get("DISPLAY", "not set")
            width, height = pyautogui.size()
            self.print_result("Display check", True, f"DISPLAY={display}, screen={width}x{height}")
        except Exception as e:
            self.print_result("Display check", False, str(e))

    def test_automation_init(self) -> None:
        """Test creating automation instance."""
        try:
            # Be conservative: pass display and output_dir if supported.
            # If GUIAutomation signature differs, user can adjust later.
            self.automation = GUIAutomation(  # type: ignore[call-arg]
                app_name=self.app_name,
                output_dir=str(self.output_dir),
                display=self.display,
            )
            self.print_result("Automation init", True)
        except TypeError:
            # Fallback: minimal init
            try:
                self.automation = GUIAutomation(  # type: ignore[call-arg]
                    app_name=self.app_name,
                    output_dir=str(self.output_dir),
                )
                self.print_result("Automation init", True, "(fallback init: no display arg)")
            except Exception as e:
                self.print_result("Automation init", False, str(e))
        except Exception as e:
            self.print_result("Automation init", False, str(e))

    def test_launch_app(self) -> None:
        """Test launching application."""
        if not self._require_automation("Launch app"):
            return

        try:
            ok = bool(self.automation.launch_app())  # type: ignore[union-attr]
            pid = getattr(getattr(self.automation, "app_process", None), "pid", None)
            self.print_result("Launch app", ok, f"PID={pid}" if pid else "")
        except AppLaunchError as e:
            self.print_result("Launch app", False, str(e))
        except DisplayNotFoundError as e:
            self.print_result("Launch app", False, str(e))
        except Exception as e:
            self.print_result("Launch app", False, f"Unexpected error: {e}")

    def test_screenshot(self) -> None:
        """Test taking screenshot."""
        if not self._require_automation("Screenshot"):
            return

        if not hasattr(self.automation, "take_screenshot"):
            self.print_skipped("Screenshot", "GUIAutomation.take_screenshot not implemented")
            return

        try:
            path = self.automation.take_screenshot("test_screenshot")  # type: ignore[union-attr]
            screenshot_path = Path(path) if not isinstance(path, Path) else path

            if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
                self.print_result(
                    "Screenshot",
                    True,
                    f"Saved: {screenshot_path} ({screenshot_path.stat().st_size} bytes)",
                )
            else:
                self.print_result("Screenshot", False, "File not created or empty")
        except ScreenshotError as e:
            self.print_result("Screenshot", False, str(e))
        except Exception as e:
            self.print_result("Screenshot", False, f"Unexpected error: {e}")

    def test_click(self) -> None:
        """Test performing a click."""
        if not self._require_automation("Click"):
            return

        if not hasattr(self.automation, "perform_action"):
            self.print_skipped("Click", "GUIAutomation.perform_action not implemented")
            return

        pyautogui = self._safe_import_pyautogui()

        try:
            width, height = pyautogui.size()
            x, y = width // 2, height // 2

            action = {
                "action_type": "click",
                "coordinates": (x, y),
                "parameters": {"button": "left", "clicks": 1},
            }
            self.automation.perform_action(action)  # type: ignore[union-attr]
            self.print_result("Click", True, f"Clicked at ({x}, {y})")
        except Exception as e:
            self.print_result("Click", False, str(e))

    def test_before_after_step(self) -> None:
        """
        Test before/after screenshot artifacts via a single step, if supported.

        If GUIAutomation.run_step is not implemented yet, we skip.
        """
        if not self._require_automation("Before/After step"):
            return

        if not hasattr(self.automation, "run_step"):
            self.print_skipped("Before/After step", "GUIAutomation.run_step not implemented")
            return

        pyautogui = self._safe_import_pyautogui()

        try:
            width, height = pyautogui.size()
            x, y = width // 2, height // 2

            step = self.automation.run_step(  # type: ignore[union-attr]
                step_id=0,
                action_config={
                    "action_type": "click",
                    "coordinates": (x, y),
                    "parameters": {"button": "left", "clicks": 1},
                },
            )

            # We tolerate different step representations (dataclass/dict).
            before_path = getattr(step, "before_screenshot", None) or getattr(step, "before", None)
            after_path = getattr(step, "after_screenshot", None) or getattr(step, "after", None)
            metadata = getattr(step, "metadata", None)

            if before_path is None or after_path is None:
                self.print_result("Before/After step", False, "Step object missing before/after paths")
                return

            before_exists = Path(str(before_path)).exists()
            after_exists = Path(str(after_path)).exists()

            if before_exists and after_exists:
                changed = None
                if isinstance(metadata, dict):
                    changed = metadata.get("changed")
                msg = f"Artifacts ok" + (f", changed={changed}" if changed is not None else "")
                self.print_result("Before/After step", True, msg)
            else:
                missing = []
                if not before_exists:
                    missing.append("before")
                if not after_exists:
                    missing.append("after")
                self.print_result("Before/After step", False, f"Missing: {missing}")
        except Exception as e:
            self.print_result("Before/After step", False, str(e))

    def test_close_app(self) -> None:
        """Test closing application."""
        if not self._require_automation("Close app"):
            return

        if not hasattr(self.automation, "close_app"):
            self.print_skipped("Close app", "GUIAutomation.close_app not implemented")
            return

        try:
            ok = bool(self.automation.close_app())  # type: ignore[union-attr]
            self.print_result("Close app", ok)
        except Exception as e:
            self.print_result("Close app", False, str(e))

    def test_calculator_digit_5_optional(self) -> None:
        """
        Optional test: click digit_5 using calibrated coordinates (if supported).

        This test only runs if:
        - get_button_coordinates exists
        - compute_image_hash exists
        - take_screenshot exists
        """
        if self.automation is None:
            self.print_skipped("Calculator digit_5 test", "No automation instance")
            return

        required = ["get_button_coordinates", "take_screenshot", "perform_action", "compute_image_hash"]
        missing = [m for m in required if not hasattr(self.automation, m)]
        if missing:
            self.print_skipped("Calculator digit_5 test", f"Missing methods: {missing}")
            return

        try:
            coords = self.automation.get_button_coordinates("digit_5")  # type: ignore[union-attr]
            if not coords:
                self.print_skipped("Calculator digit_5 test", "No digit_5 coordinates available")
                return

            # Normalize coords to tuple[int, int]
            x, y = self._normalize_coords(coords)

            before = self.automation.take_screenshot("calc_test_before")  # type: ignore[union-attr]
            before_path = Path(before) if not isinstance(before, Path) else before

            self.automation.perform_action(  # type: ignore[union-attr]
                {
                    "action_type": "click",
                    "coordinates": (x, y),
                    "parameters": {"button": "left", "clicks": 1},
                }
            )
            time.sleep(0.3)

            after = self.automation.take_screenshot("calc_test_after")  # type: ignore[union-attr]
            after_path = Path(after) if not isinstance(after, Path) else after

            before_hash = self.automation.compute_image_hash(before_path)  # type: ignore[union-attr]
            after_hash = self.automation.compute_image_hash(after_path)  # type: ignore[union-attr]

            changed = before_hash != after_hash
            self.print_result("Calculator digit_5 test", True, f"clicked ({x},{y}), changed={changed}")
        except Exception as e:
            self.print_result("Calculator digit_5 test", False, str(e))

    @staticmethod
    def _normalize_coords(coords: Any) -> Tuple[int, int]:
        """
        Accept coordinates in a few common forms:
          - (x, y)
          - [x, y]
          - {"x": x, "y": y}
        """
        if isinstance(coords, tuple) and len(coords) == 2:
            return int(coords[0]), int(coords[1])
        if isinstance(coords, list) and len(coords) == 2:
            return int(coords[0]), int(coords[1])
        if isinstance(coords, dict) and "x" in coords and "y" in coords:
            return int(coords["x"]), int(coords["y"])
        raise ValueError(f"Unsupported coordinates format: {coords!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test GUI automation infrastructure (Phase 0.3)")
    parser.add_argument("--app", default="gnome-calculator", help="Application to test")
    parser.add_argument("--display", default=":99", help="X11 display (e.g., :99)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    tester = AutomationTester(app_name=args.app, display=args.display)

    try:
        tester.run_all_tests()
        return 1 if tester.test_failed > 0 else 0
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
        return 130
    except GUIDistillationError as e:
        print(f"\n❌ Project error: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
