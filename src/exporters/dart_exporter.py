"""
DART-like episode exporter.

Converts an internal EpisodeRecord into the DART bundle structure:

    <dart_root>/pyautogui/screenshot/gui2mcp_agent/<app_id>/<episode_uuid>/
        traj.jsonl
        result.txt
        step_1_<timestamp>.png
        step_2_<timestamp>.png
        ...
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from src.domain.models import EpisodeRecord, StepRecord

logger = logging.getLogger(__name__)


class DartExporter:
    """Converts an EpisodeRecord to a DART-like on-disk bundle."""

    def export(
        self,
        episode: EpisodeRecord,
        dart_root: Path,
        internal_episode_dir: Path,
    ) -> Path:
        """
        Write the DART bundle and return the bundle directory path.

        Args:
            episode:              The completed EpisodeRecord.
            dart_root:            Root of the DART output tree (e.g. data/exported_dart).
            internal_episode_dir: Directory where internal artifacts were written
                                  (screenshots, A11Y XMLs, etc.).
        """
        bundle_dir = (
            dart_root
            / "pyautogui"
            / "screenshot"
            / "gui2mcp_agent"
            / episode.app_id
            / episode.episode_uuid
        )
        bundle_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copy screenshots with DART naming: step_N_<timestamp>.png
        screenshot_map: dict[str, str] = {}  # internal filename → DART filename
        for step in episode.steps:
            src = internal_episode_dir / step.screenshot_file
            if not src.exists():
                logger.warning("Screenshot not found: %s", src)
                continue
            dart_name = f"step_{step.step_id + 1}_{step.timestamp}.png"
            dst = bundle_dir / dart_name
            shutil.copy2(src, dst)
            screenshot_map[step.screenshot_file] = dart_name

        # 2. Write traj.jsonl (one JSON object per line)
        traj_path = bundle_dir / "traj.jsonl"
        with traj_path.open("w", encoding="utf-8") as f:
            for step in episode.steps:
                dart_screenshot = screenshot_map.get(step.screenshot_file, step.screenshot_file)
                row = self._step_to_dart(step, dart_screenshot)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        # 3. Write result.txt
        score = episode.final_score if episode.final_score is not None else 0.0
        (bundle_dir / "result.txt").write_text(str(score), encoding="utf-8")

        logger.info(
            "DART bundle written → %s (%d steps, score=%.2f)",
            bundle_dir, len(episode.steps), score,
        )
        return bundle_dir

    def _step_to_dart(self, step: StepRecord, dart_screenshot: str) -> dict:
        """Convert one StepRecord to a DART traj.jsonl row."""
        action_str = "DONE" if step.done else (step.planner_action or "")
        response_str = ""
        if step.planner_thought:
            response_str = f"Thought: {step.planner_thought}"
        if step.planner_action:
            response_str += f"\nAction: {step.planner_action}"

        return {
            "step_num": step.step_id + 1,
            "action_timestamp": step.timestamp,
            "action": action_str,
            "response": response_str.strip(),
            "reward": step.step_reward,
            "done": step.done,
            "info": step.info,
            "screenshot_file": dart_screenshot,
        }
