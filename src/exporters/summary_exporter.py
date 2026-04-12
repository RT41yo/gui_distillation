"""
Summary exporter — builds all_result.json and summary/results.json
by scanning the DART output tree.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Fixed paths within DART root
_AGENT_DIR = Path("pyautogui") / "screenshot" / "gui2mcp_agent"
_SUMMARY_DIR = Path("summary")


class SummaryExporter:
    """Scans DART bundles and writes aggregated result files."""

    def export(self, dart_root: Path) -> None:
        """
        Re-scan all DART bundles under dart_root and write:
          - <dart_root>/pyautogui/screenshot/gui2mcp_agent/all_result.json
          - <dart_root>/summary/results.json
        """
        agent_dir = dart_root / _AGENT_DIR

        all_result: Dict[str, Dict[str, Any]] = {}
        summary_rows: List[Dict[str, Any]] = []

        if not agent_dir.exists():
            logger.warning("DART agent dir not found: %s", agent_dir)
            return

        for app_dir in sorted(agent_dir.iterdir()):
            if not app_dir.is_dir() or app_dir.name in {"all_result.json", "args.json"}:
                continue
            app_id = app_dir.name
            all_result[app_id] = {}

            for episode_dir in sorted(app_dir.iterdir()):
                if not episode_dir.is_dir():
                    continue
                episode_uuid = episode_dir.name
                result_file = episode_dir / "result.txt"
                if not result_file.exists():
                    continue

                raw = result_file.read_text(encoding="utf-8").strip()
                try:
                    score = float(raw)
                except ValueError:
                    score = 0.0

                all_result[app_id][episode_uuid] = score
                summary_rows.append({
                    "application": app_id,
                    "task_id": episode_uuid,
                    "status": "success",
                    "score": score,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

        # Write all_result.json
        all_result_path = agent_dir / "all_result.json"
        all_result_path.write_text(
            json.dumps(all_result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("all_result.json written → %s", all_result_path)

        # Write summary/results.json
        summary_dir = dart_root / _SUMMARY_DIR
        summary_dir.mkdir(parents=True, exist_ok=True)
        results_path = summary_dir / "results.json"
        results_path.write_text(
            json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("results.json written → %s (%d episodes)", results_path, len(summary_rows))
