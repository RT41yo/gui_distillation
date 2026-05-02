from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ui_explorer.app.launcher import AppLauncher
from ui_explorer.app.registry import AppRegistry
from ui_explorer.core.a11y_capture import A11YCapture


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture A11Y XML for an app.")
    parser.add_argument("--app", required=True)
    parser.add_argument("--display", default=":99")
    parser.add_argument("--apps-config", default="config/apps.yaml")
    parser.add_argument("--output", default="data/maps")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
    )

    app_cfg = AppRegistry(Path(args.apps_config)).get(args.app)

    if args.launch:
        AppLauncher().launch(app_cfg.launcher, display=args.display)

    out_dir = Path(args.output) / app_cfg.app_id / "_captures"
    xml_path = out_dir / "a11y_tree.xml"

    A11YCapture().capture_to_xml(
        a11y_name=app_cfg.a11y_name,
        output_path=xml_path,
        timeout_s=args.timeout,
    )

    print(xml_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
