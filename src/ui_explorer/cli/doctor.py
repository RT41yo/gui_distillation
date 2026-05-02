from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ui-explorer project setup.")
    parser.add_argument("--apps", default="config/apps.yaml")
    parser.add_argument("--settings", default="config/settings.yaml")
    args = parser.parse_args()

    apps_path = Path(args.apps)
    settings_path = Path(args.settings)

    if not apps_path.exists():
        print(f"ERROR: apps config not found: {apps_path}")
        return 1

    if not settings_path.exists():
        print(f"ERROR: settings config not found: {settings_path}")
        return 1

    apps = yaml.safe_load(apps_path.read_text(encoding="utf-8")) or {}
    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}

    app_count = len(apps.get("apps", []))
    display = settings.get("runtime", {}).get("display")

    print("ui-explorer setup OK")
    print(f"apps: {app_count}")
    print(f"display: {display}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
