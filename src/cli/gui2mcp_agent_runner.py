"""
CLI entrypoint for the gui2mcp agent.

Usage example:
    python -m src.cli.gui2mcp_agent_runner \\
        --app calc \\
        --task-mode \\
        --task-id calc_001 \\
        --max-steps 20 \\
        --output data/trajectory_runs/run_001
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gui2mcp_agent_runner",
        description="A11Y-first GUI Trajectory Agent with DART-like export",
    )
    parser.add_argument("--app", required=True, help="App ID from app_basket.yaml (calc, writer, gedit)")
    parser.add_argument("--task-mode", action="store_true", help="Run in task mode (use task basket)")
    parser.add_argument("--task-id", default=None, help="Specific task ID (optional; random if omitted)")
    parser.add_argument("--max-steps", type=int, default=20, help="Max steps per episode")
    parser.add_argument("--output", default="data/trajectory_runs", help="Internal artifacts output dir")
    parser.add_argument("--dart-output", default="data/exported_dart", help="DART export root dir")
    parser.add_argument("--display", default=":99", help="X11 display (e.g. :99)")
    parser.add_argument("--screen-width", type=int, default=1280, help="Screen width in pixels")
    parser.add_argument("--screen-height", type=int, default=1024, help="Screen height in pixels")
    parser.add_argument("--settings", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument("--llm-config", default=None, help="Override planner LLM config path")
    parser.add_argument(
        "--locator-mode",
        choices=["a11y", "a11y_with_vlm_fallback", "vlm_only"],
        default="a11y_with_vlm_fallback",
        help="Locator strategy (default: a11y_with_vlm_fallback)",
    )
    parser.add_argument("--app-basket", default="config/app_basket.yaml")
    parser.add_argument("--task-basket", default="config/task_basket.yaml")
    parser.add_argument("--startup-wait", type=float, default=3.0, help="Seconds to wait after app launch")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    # Import here to keep startup fast and allow --help without heavy imports
    from src.agents.gui2mcp_agent import Gui2MCPAgent

    planner_config = args.llm_config or "config/llm/planner_gpt-5.4-mini.yaml"
    locator_config = "config/llm/locator_gpt-5.4-mini.yaml"

    agent = Gui2MCPAgent(
        base_output_dir=Path(args.output),
        dart_root=Path(args.dart_output),
        display=args.display,
        settings_path=args.settings,
        planner_config=planner_config,
        locator_config=locator_config,
        app_basket=args.app_basket,
        task_basket=args.task_basket,
        max_steps=args.max_steps,
        startup_wait=args.startup_wait,
        screen_width=args.screen_width,
        screen_height=args.screen_height,
    )

    episode = agent.run_episode(app_id=args.app, task_id=args.task_id)

    print(f"\nEpisode complete:")
    print(f"  app       : {episode.app_id}")
    print(f"  task      : {episode.task_id}")
    print(f"  steps     : {episode.total_steps}")
    print(f"  score     : {episode.final_score}")
    print(f"  success   : {episode.success}")
    print(f"  uuid      : {episode.episode_uuid}")

    return 0 if episode.success else 1


if __name__ == "__main__":
    sys.exit(main())
