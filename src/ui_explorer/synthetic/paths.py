from __future__ import annotations

from pathlib import Path

DEFAULT_OUTPUT_ROOT = Path("data/synthetic/libreoffice_writer/active_root_231")
SCOPE_MAP_PATH = Path("data/maps/libreoffice_writer/agent_map_active_root_scope.json")
AGENT_MAP_PATH = Path("data/maps/libreoffice_writer/agent_map.json")
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

CLASSIFICATION_DIRNAME = "classification"
TASK_GENERATION_DIRNAME = "task_generation"
LOGS_DIRNAME = ".logs"

# Model used for the bulk of existing yield classifications on disk.
DEFAULT_CLASSIFICATION_MODEL = "gpt-4o-mini-2024-07-18"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return repo_root() / path
