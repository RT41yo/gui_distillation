"""
Task registry — loads and provides access to task_basket.yaml entries.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from src.domain.models import TaskConfig


class TaskRegistry:
    """Loads task_basket.yaml and provides lookup and selection by app_id."""

    def __init__(self, config_path: str | Path = "config/task_basket.yaml") -> None:
        self._path = Path(config_path)
        self._tasks: Dict[str, List[TaskConfig]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            raise FileNotFoundError(f"task_basket.yaml not found at {self._path}")
        data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        tasks_raw = data.get("tasks", {})
        if not isinstance(tasks_raw, dict):
            raise ValueError(f"'tasks' in {self._path} must be a mapping")
        for app_id, task_list in tasks_raw.items():
            self._tasks[app_id] = [TaskConfig(**t) for t in (task_list or [])]

    def get(self, app_id: str, task_id: str) -> TaskConfig:
        """Return a specific task by app_id and task_id."""
        tasks = self._tasks.get(app_id, [])
        for t in tasks:
            if t.task_id == task_id:
                return t
        raise KeyError(f"Task '{task_id}' not found for app '{app_id}'")

    def list(self, app_id: str) -> List[TaskConfig]:
        """Return all tasks for an app."""
        return list(self._tasks.get(app_id, []))

    def select_random(self, app_id: str) -> TaskConfig:
        """Return a random task for an app."""
        tasks = self._tasks.get(app_id)
        if not tasks:
            raise ValueError(f"No tasks defined for app '{app_id}'")
        return random.choice(tasks)
