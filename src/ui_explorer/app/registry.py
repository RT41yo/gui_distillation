from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class AppConfig:
    app_id: str
    display_name: str
    launcher: str
    a11y_name: str


class AppRegistry:
    def __init__(self, config_path: Path = Path("config/apps.yaml")) -> None:
        self.config_path = config_path

    def get(self, app_id: str) -> AppConfig:
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        for item in data.get("apps", []):
            if item.get("app_id") == app_id:
                return AppConfig(
                    app_id=item["app_id"],
                    display_name=item.get("display_name", item["app_id"]),
                    launcher=item["launcher"],
                    a11y_name=item["a11y_name"],
                )
        raise KeyError(f"App '{app_id}' not found in {self.config_path}")
