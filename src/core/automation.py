# src/core/automation.py
"""
GUI Automation core module.

Phase: 0.3 Infrastructure Setup

Responsibilities:
- Application lifecycle (launch, close)
- Screenshot capture (before/after)
- Execute simple actions (click/type/press/move_to/hotkey)
- Save step artifacts in a reproducible structure

This module is driven by config/settings.yaml (runtime config).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pyautogui

from src.core.exceptions import (
    ActionExecutionError,
    AppCloseError,
    AppLaunchError,
    AppNotFoundError,
    CoordinatesError,
    DisplayNotFoundError,
    ScreenshotError,
)

logger = logging.getLogger(__name__)


JsonDict = Dict[str, Any]
Coords = Tuple[int, int]


@dataclass(frozen=True)
class StepArtifacts:
    """Paths to step artifacts on disk."""
    step_dir: Path
    before: Optional[Path]
    after: Optional[Path]
    metadata: Path


class GUIAutomation:
    """
    Main class for GUI automation.

    Config precedence:
    - settings.yaml (base)
    - settings.yaml overrides[runtime.profile] deep-merged
    - explicit constructor args override config
    """

    def __init__(
        self,
        app_name: str,
        output_dir: Optional[str] = None,
        display: Optional[str] = None,
        settings_path: str = "config/settings.yaml",
        app_config_path: Optional[str] = None,
    ) -> None:
        self.settings_path = Path(settings_path)
        self.settings = self._load_settings(self.settings_path)

        self.app_name = app_name

        # Runtime / display
        cfg_display = self._get(self.settings, "environment.display.display_num", ":99")
        self.display = display or cfg_display

        # Output directory (default: data/test_automation or data/exploration/... later)
        cfg_default_out = self._get(self.settings, "paths.raw_data", "data/raw")
        self.output_dir = Path(output_dir or cfg_default_out)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Coordinate system and screen geometry
        self.coordinate_system = self._get(self.settings, "automation.mouse.coordinate_system", "absolute")
        self.validate_bounds = bool(self._get(self.settings, "automation.mouse.validate_bounds", True))

        self.screen_width = int(self._get(self.settings, "environment.display.screen.width", 1280))
        self.screen_height = int(self._get(self.settings, "environment.display.screen.height", 1024))

        # Timing
        self.action_delay = float(self._get(self.settings, "automation.timing.action_delay", 0.5))
        self.screenshot_delay = float(self._get(self.settings, "automation.timing.screenshot_delay", 1.0))
        self.launch_delay = float(self._get(self.settings, "automation.timing.launch_delay", 2.0))

        # Screenshot naming / format
        self.screenshot_format = str(self._get(self.settings, "automation.screenshots.format", "png")).lower()
        if self.screenshot_format not in {"png", "jpg", "jpeg"}:
            raise ValueError(f"Unsupported screenshot format: {self.screenshot_format}")

        self.naming_pattern = str(self._get(self.settings, "automation.screenshots.naming_pattern", "step_{step_id:04d}_{suffix}.{ext}"))

        # Step filenames (Phase-1 compatible)
        self.step_file_before = str(self._get(self.settings, "data.step_files.before", "before.png"))
        self.step_file_after = str(self._get(self.settings, "data.step_files.after", "after.png"))
        self.step_file_metadata = str(self._get(self.settings, "data.step_files.metadata", "metadata.json"))

        # Hash
        self.hash_algorithm = str(self._get(self.settings, "automation.hash.algorithm", "md5")).lower()
        self.compare_hashes = bool(self._get(self.settings, "automation.hash.compare", True))

        # App config (button coordinates)
        self.app_config: JsonDict = {}
        if app_config_path:
            self.app_config = self._load_yaml(Path(app_config_path))

        # process handle
        self.app_process: Optional[subprocess.Popen[Any]] = None

        self._ensure_display()
        self._configure_pyautogui()

        logger.info("GUIAutomation initialized")
        logger.info("  app_name=%s", self.app_name)
        logger.info("  display=%s", self.display)
        logger.info("  output_dir=%s", self.output_dir)
        logger.info("  coordinate_system=%s", self.coordinate_system)
        logger.info("  screenshot_format=%s", self.screenshot_format)

    # -----------------------------
    # Settings loading / helpers
    # -----------------------------
    def _load_settings(self, path: Path) -> JsonDict:
        if not path.exists():
            logger.warning("settings.yaml not found at %s; using empty settings", path)
            return {}

        data = self._load_yaml(path)

        profile = self._get(data, "runtime.profile", None)
        overrides = self._get(data, "overrides", {}) if isinstance(data, dict) else {}
        if profile and isinstance(overrides, dict) and profile in overrides:
            base = dict(data)
            merged = self._deep_merge(base, overrides[profile])
            return merged

        return data

    @staticmethod
    def _deep_merge(base: JsonDict, override: JsonDict) -> JsonDict:
        """Deep-merge override into base (dicts only)."""
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = GUIAutomation._deep_merge(base[k], v)  # type: ignore[arg-type]
            else:
                base[k] = v
        return base

    @staticmethod
    def _get(dct: JsonDict, dotted_path: str, default: Any) -> Any:
        cur: Any = dct
        for part in dotted_path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    @staticmethod
    def _load_yaml(path: Path) -> JsonDict:
        try:
            import yaml  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("PyYAML is required to load YAML configs. Install pyyaml.") from e

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}

    # -----------------------------
    # Environment / display
    # -----------------------------
    def _ensure_display(self) -> None:
        # set for this process
        os.environ["DISPLAY"] = self.display

        # simple probe
        try:
            _w, _h = pyautogui.size()
            logger.info("Display reachable: %sx%s (DISPLAY=%s)", _w, _h, self.display)
        except Exception as e:
            raise DisplayNotFoundError(self.display) from e

    def _configure_pyautogui(self) -> None:
        pyautogui.FAILSAFE = bool(self._get(self.settings, "automation.pyautogui.failsafe", True))
        pyautogui.PAUSE = float(self._get(self.settings, "automation.pyautogui.pause", 0.5))

    # -----------------------------
    # App lifecycle
    # -----------------------------
    def launch_app(self) -> bool:
        logger.info("Launching %s...", self.app_name)

        try:
            which_result = subprocess.run(["which", self.app_name], capture_output=True, text=True)
            if which_result.returncode != 0:
                raise AppNotFoundError(self.app_name)

            self.app_process = subprocess.Popen(
                [self.app_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
            )

            time.sleep(self.launch_delay)

            if self.app_process.poll() is not None:
                raise AppLaunchError(self.app_name, "Process exited immediately after launch")

            logger.info("%s launched (PID=%s)", self.app_name, self.app_process.pid)
            return True

        except AppNotFoundError:
            raise
        except Exception as e:
            raise AppLaunchError(self.app_name, str(e)) from e

    def close_app(self) -> bool:
        if self.app_process is None:
            logger.warning("close_app called but no process exists")
            return False

        logger.info("Closing %s...", self.app_name)

        try:
            self.app_process.terminate()

            graceful_timeout = float(self._get(self.settings, "app.gnome-calculator.close.graceful_timeout", 5))
            end = time.monotonic() + graceful_timeout
            while time.monotonic() < end:
                if self.app_process.poll() is not None:
                    logger.info("Application closed gracefully")
                    return True
                time.sleep(0.1)

            force_kill = bool(self._get(self.settings, "app.gnome-calculator.close.force_kill", True))
            if force_kill:
                logger.warning("Application did not close gracefully; killing...")
                self.app_process.kill()
                self.app_process.wait(timeout=2)
                logger.info("Application killed")
                return True

            raise AppCloseError(self.app_name, "Graceful close timed out and force_kill=false")

        except Exception as e:
            raise AppCloseError(self.app_name, str(e)) from e

    # -----------------------------
    # Screenshots / hashing
    # -----------------------------
    def take_screenshot(self, path: Union[str, Path]) -> Path:
        """
        Take a screenshot and save to the specified path.

        Accepts:
        - Path: full path including filename
        - str: either full path or just a filename (with or without extension)

        Returns:
        Path to the saved screenshot.
        """
        try:
            out_path = Path(path)

            # If user passed only a stem (e.g. "test_screenshot"), add extension
            if out_path.suffix == "":
                out_path = out_path.with_suffix(f".{self.screenshot_format}")

            # If user passed a relative path, resolve it relative to the output directory
            if not out_path.is_absolute():
                out_path = self.output_dir / out_path

            out_path.parent.mkdir(parents=True, exist_ok=True)

            img = pyautogui.screenshot()

            pil_format = "PNG" if self.screenshot_format.lower() == "png" else "JPEG"
            save_kwargs: Dict[str, Any] = {}

            if pil_format == "JPEG":
                # In settings.yaml you used "quality". Let's support both keys safely.
                quality = self._get(self.settings, "automation.screenshots.quality", None)
                jpeg_quality = self._get(self.settings, "automation.screenshots.jpeg_quality", None)
                q = jpeg_quality if jpeg_quality is not None else (quality if quality is not None else 95)
                save_kwargs["quality"] = int(q)

            img.save(out_path, format=pil_format, **save_kwargs)
            return out_path

        except Exception as e:
            raise ScreenshotError(str(e)) from e

        def compute_image_hash(self, image_path: Path) -> str:
            algo = self.hash_algorithm
            h = hashlib.new(algo)
            with image_path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()

    # -----------------------------
    # Coordinates utilities
    # -----------------------------
    def _to_absolute_coords(self, coords: Union[Coords, Tuple[float, float]]) -> Coords:
        """
        Convert coordinates to absolute pixels depending on coordinate_system.
        - If coordinate_system == "absolute": expects ints
        - If coordinate_system == "normalized": expects floats in [0,1]
        """
        if self.coordinate_system == "absolute":
            x, y = coords
            return int(x), int(y)

        # normalized
        x_f, y_f = coords
        x = int(round(float(x_f) * (self.screen_width - 1)))
        y = int(round(float(y_f) * (self.screen_height - 1)))
        return x, y

    def _validate_coords(self, x: int, y: int) -> None:
        if not self.validate_bounds:
            return
        if x < 0 or y < 0:
            raise CoordinatesError(x, y, "negative coordinates")
        if x >= self.screen_width or y >= self.screen_height:
            raise CoordinatesError(x, y, f"outside screen bounds ({self.screen_width}x{self.screen_height})")

    # -----------------------------
    # Actions
    # -----------------------------
    def perform_action(self, action_config: JsonDict) -> None:
        """
        Execute an action.

        Supported normalized schema (preferred):
          {
            "action_type": "click",
            "coordinates": [x, y] | (x, y) | {"x":x,"y":y},
            "parameters": {"button": "left", "clicks": 1}
          }

        Backward-compatible fields:
          - button, clicks at top-level
          - text/key/keys
        """
        action_type = str(action_config.get("action_type", "click"))
        params = dict(action_config.get("parameters", {}))

        # Backward compat
        if "button" in action_config and "button" not in params:
            params["button"] = action_config["button"]
        if "clicks" in action_config and "clicks" not in params:
            params["clicks"] = action_config["clicks"]
        if "text" in action_config and "text" not in params:
            params["text"] = action_config["text"]
        if "key" in action_config and "key" not in params:
            params["key"] = action_config["key"]
        if "keys" in action_config and "keys" not in params:
            params["keys"] = action_config["keys"]
        if "duration" in action_config and "duration" not in params:
            params["duration"] = action_config["duration"]

        coords_any = action_config.get("coordinates")
        coords: Optional[Coords] = None
        if coords_any is not None:
            coords = self._normalize_coords(coords_any)
            coords = self._to_absolute_coords(coords)
            self._validate_coords(coords[0], coords[1])

        logger.info("Executing action: %s (coords=%s)", action_type, coords)

        try:
            if action_type == "click":
                button = str(params.get("button", "left"))
                clicks = int(params.get("clicks", 1))
                if coords:
                    pyautogui.click(x=coords[0], y=coords[1], button=button, clicks=clicks)
                else:
                    pyautogui.click(button=button, clicks=clicks)

            elif action_type == "double_click":
                button = str(params.get("button", "left"))
                if coords:
                    pyautogui.doubleClick(x=coords[0], y=coords[1], button=button)
                else:
                    pyautogui.doubleClick(button=button)

            elif action_type == "right_click":
                if coords:
                    pyautogui.rightClick(x=coords[0], y=coords[1])
                else:
                    pyautogui.rightClick()

            elif action_type == "move_to":
                if coords is None:
                    raise ActionExecutionError(action_type, "move_to requires coordinates")
                duration = float(params.get("duration", self._get(self.settings, "automation.timing.move_duration", 0.5)))
                pyautogui.moveTo(coords[0], coords[1], duration=duration)

            elif action_type == "type":
                text = str(params.get("text", ""))
                pyautogui.write(text, interval=float(self._get(self.settings, "automation.timing.type_delay", 0.1)))

            elif action_type == "press":
                key = str(params.get("key", "enter"))
                pyautogui.press(key)

            elif action_type == "hotkey":
                keys = params.get("keys", [])
                if not isinstance(keys, list) or not keys:
                    raise ActionExecutionError(action_type, "hotkey requires parameters.keys as non-empty list")
                pyautogui.hotkey(*[str(k) for k in keys])

            else:
                raise ActionExecutionError(action_type, f"Unsupported action_type: {action_type}")

            time.sleep(self.screenshot_delay)

        except CoordinatesError:
            raise
        except ActionExecutionError:
            raise
        except Exception as e:
            raise ActionExecutionError(action_type, str(e)) from e

    @staticmethod
    def _normalize_coords(coords: Any) -> Union[Coords, Tuple[float, float]]:
        if isinstance(coords, tuple) and len(coords) == 2:
            return coords[0], coords[1]
        if isinstance(coords, list) and len(coords) == 2:
            return coords[0], coords[1]
        if isinstance(coords, dict) and "x" in coords and "y" in coords:
            return coords["x"], coords["y"]
        raise ValueError(f"Unsupported coordinates format: {coords!r}")

    # -----------------------------
    # Step execution
    # -----------------------------
    def run_step(self, step_id: int, action_config: JsonDict, take_before: bool = True, take_after: bool = True) -> StepArtifacts:
        """
        Run a single step:
          - create step directory
          - optionally take before screenshot
          - perform action
          - optionally take after screenshot
          - write metadata.json
        """
        step_dir = self.output_dir / f"step_{step_id:04d}"
        step_dir.mkdir(parents=True, exist_ok=True)

        before_path = step_dir / self.step_file_before if take_before else None
        after_path = step_dir / self.step_file_after if take_after else None
        meta_path = step_dir / self.step_file_metadata

        before_hash = None
        after_hash = None

        if before_path:
            self.take_screenshot(before_path)
            before_hash = self.compute_image_hash(before_path)

        self.perform_action(action_config)

        if after_path:
            self.take_screenshot(after_path)
            after_hash = self.compute_image_hash(after_path)

        changed = None
        if self.compare_hashes and before_hash and after_hash:
            changed = before_hash != after_hash

        metadata = {
            "step_id": step_id,
            "timestamp": time.time(),
            "app": self.app_name,
            "display": self.display,
            "screen": {"width": self.screen_width, "height": self.screen_height},
            "action": action_config,
            "hashes": {"before": before_hash, "after": after_hash},
            "changed": changed,
            "timing": {"action_delay": self.action_delay, "screenshot_delay": self.screenshot_delay},
        }

        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Step %s completed (changed=%s) -> %s", step_id, changed, step_dir)

        return StepArtifacts(step_dir=step_dir, before=before_path, after=after_path, metadata=meta_path)

    def run_sequence(self, actions: List[JsonDict], start_id: int = 0) -> List[StepArtifacts]:
        out: List[StepArtifacts] = []
        for i, action in enumerate(actions):
            out.append(self.run_step(start_id + i, action))
            if i < len(actions) - 1:
                time.sleep(self.action_delay)
        return out

    # -----------------------------
    # App config helpers
    # -----------------------------
    def get_button_coordinates(self, button_name: str) -> Optional[Coords]:
        buttons = self.app_config.get("buttons", {}) if isinstance(self.app_config, dict) else {}
        coords = buttons.get(button_name)
        if coords is None:
            return None
        if isinstance(coords, list) and len(coords) == 2:
            return int(coords[0]), int(coords[1])
        if isinstance(coords, tuple) and len(coords) == 2:
            return int(coords[0]), int(coords[1])
        return None

    def click_button(self, button_name: str, clicks: int = 1) -> bool:
        coords = self.get_button_coordinates(button_name)
        if not coords:
            return False
        self.perform_action(
            {
                "action_type": "click",
                "coordinates": coords,
                "parameters": {"button": "left", "clicks": clicks},
            }
        )
        return True

    # -----------------------------
    # Context manager
    # -----------------------------
    def __enter__(self) -> "GUIAutomation":
        self.launch_app()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.close_app()
        except Exception:
            # Don't mask original exceptions
            logger.exception("Failed to close app during context manager exit")


# =========================================================
# CLI (optional)
# =========================================================
def _cli() -> int:
    import argparse
    import random

    parser = argparse.ArgumentParser(description="GUI Automation Tool (Phase 0.3)")
    parser.add_argument("--app", default="gnome-calculator", help="Application to automate")
    parser.add_argument("--output", default=None, help="Output directory (default from settings)")
    parser.add_argument("--settings", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument("--app-config", default=None, help="Path to app config YAML (button coordinates)")
    parser.add_argument("--display", default=None, help="X11 display (overrides settings)")
    parser.add_argument("--steps", type=int, default=1, help="Number of random steps")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    with GUIAutomation(
        app_name=args.app,
        output_dir=args.output,
        settings_path=args.settings,
        app_config_path=args.app_config,
        display=args.display,
    ) as auto:
        width, height = pyautogui.size()
        for i in range(args.steps):
            x = random.randint(50, max(50, width - 50))
            y = random.randint(50, max(50, height - 50))
            auto.run_step(
                i,
                {
                    "action_type": "click",
                    "coordinates": (x, y),
                    "parameters": {"button": "left", "clicks": 1},
                },
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
