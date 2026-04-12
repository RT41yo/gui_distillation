"""
App registry — loads and provides access to app_basket.yaml entries.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.domain.models import AppConfig


class AppRegistry:
    """Loads app_basket.yaml and provides lookup by app_id."""

    def __init__(self, config_path: str | Path = "config/app_basket.yaml") -> None:
        self._path = Path(config_path)
        self._apps: Dict[str, AppConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"app_basket.yaml not found at {self._path}")
        data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        apps_raw = data.get("apps", [])
        if not isinstance(apps_raw, list):
            raise ValueError(f"'apps' in {self._path} must be a list")
        for item in apps_raw:
            app = AppConfig(**item)
            self._apps[app.app_id] = app

    def get(self, app_id: str) -> AppConfig:
        if app_id not in self._apps:
            raise KeyError(f"Unknown app_id '{app_id}'. Available: {list(self._apps)}")
        return self._apps[app_id]

    def all(self) -> List[AppConfig]:
        return list(self._apps.values())

    def app_ids(self) -> List[str]:
        return list(self._apps.keys())
