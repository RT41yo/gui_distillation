"""
Domain models for the gui2mcp agent.

All data contracts are defined here as Pydantic v2 models.
These are the single source of truth for step and episode structure.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration models (loaded from YAML)
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    """Single application entry from app_basket.yaml."""
    app_id: str
    display_name: str
    launcher: str
    a11y_app_name: str
    mode: str = "a11y_first"
    evaluator: str


class TaskConfig(BaseModel):
    """Single task entry from task_basket.yaml."""
    task_id: str
    instruction: str
    category: str
    evaluator: str
    expected_text: Optional[str] = None


# ---------------------------------------------------------------------------
# Runtime action / locator models
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    CLICK = "click"
    TYPE_TEXT = "type_text"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    WAIT = "wait"
    DONE = "done"


class LocatorResult(BaseModel):
    """Result from any locator backend (A11Y or VLM)."""
    source: str                            # "a11y" or "vlm"
    found: bool
    element_name: Optional[str] = None
    bbox: Optional[List[float]] = None    # [x, y, w, h] in pixels
    center: Optional[Tuple[float, float]] = None
    confidence: Optional[float] = None
    raw: Optional[Dict[str, Any]] = None  # full raw response for debugging


class PlannerResponse(BaseModel):
    """Parsed response from the planner LLM."""
    thought: str
    target_query: str
    action_type: ActionType
    text: Optional[str] = None            # for type_text
    keys: Optional[List[str]] = None      # for hotkey
    done: bool = False
    raw_response: Optional[str] = None


class ExecutorAction(BaseModel):
    """Concrete action passed to the executor."""
    tool: str                             # "click", "type_text", "hotkey", "scroll", "wait"
    x: Optional[float] = None
    y: Optional[float] = None
    button: str = "left"
    text: Optional[str] = None
    keys: Optional[List[str]] = None
    direction: Optional[str] = None
    amount: int = 3
    duration: float = 0.5


# ---------------------------------------------------------------------------
# Step record (internal rich format)
# ---------------------------------------------------------------------------

class IoURecord(BaseModel):
    """Per-step IoU between A11Y bbox and VLM bbox."""
    a11y_bbox: Optional[List[float]] = None    # ground truth
    vlm_bbox: Optional[List[float]] = None     # prediction
    iou_score: Optional[float] = None
    center_error_px: Optional[float] = None


class DHashRecord(BaseModel):
    """dHash and Hamming distance for a step."""
    before_dhash: Optional[str] = None
    after_dhash: Optional[str] = None
    hamming_distance: Optional[int] = None


class StepRecord(BaseModel):
    """Full internal record for a single agent step."""
    step_id: int
    task_id: str
    app_id: str
    task_text: str
    timestamp: str                            # "YYYYMMDD@HHMMSSffffff"
    screenshot_file: str
    a11y_tree_file: Optional[str] = None
    a11y_buttons_file: Optional[str] = None
    planner_raw_response: Optional[str] = None
    planner_thought: Optional[str] = None
    planner_action: Optional[str] = None      # human-readable e.g. "click('Settings')"
    locator_source: Optional[str] = None      # "a11y" or "vlm"
    locator_result: Optional[LocatorResult] = None
    executor_action: Optional[ExecutorAction] = None
    tool_calls: List[str] = Field(default_factory=list)
    iou: Optional[IoURecord] = None
    dhash: Optional[DHashRecord] = None
    step_reward: float = 0.0
    done: bool = False
    info: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Episode record (internal rich format)
# ---------------------------------------------------------------------------

class EpisodeRecord(BaseModel):
    """Full internal record for a complete episode."""
    episode_uuid: str
    app_id: str
    app_display_name: str
    task_id: str
    task_instruction: str
    steps: List[StepRecord] = Field(default_factory=list)
    final_score: Optional[float] = None
    success: bool = False
    evaluator_output: Dict[str, Any] = Field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    total_steps: int = 0
    locator_source_counts: Dict[str, int] = Field(default_factory=dict)
