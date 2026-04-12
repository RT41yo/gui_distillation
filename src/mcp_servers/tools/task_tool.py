"""
MCP-style task tools: select from basket, render instruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.domain.models import TaskConfig
from src.domain.task_registry import TaskRegistry


@dataclass
class SelectTaskInput:
    app_id: str
    task_id: Optional[str] = None  # None → random


@dataclass
class SelectTaskOutput:
    task: TaskConfig


class SelectTaskTool:
    """Select a task from task_basket.yaml for a given app."""

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def run(self, inp: SelectTaskInput) -> SelectTaskOutput:
        if inp.task_id:
            task = self._registry.get(inp.app_id, inp.task_id)
        else:
            task = self._registry.select_random(inp.app_id)
        return SelectTaskOutput(task=task)


# ---------------------------------------------------------------------------

@dataclass
class RenderTaskInput:
    task: TaskConfig


@dataclass
class RenderTaskOutput:
    instruction: str


class RenderTaskTool:
    """
    Return the natural-language instruction for a task.

    Currently returns the instruction as-is. Could be extended to call
    an LLM for rephrasing without changing the interface.
    """

    def run(self, inp: RenderTaskInput) -> RenderTaskOutput:
        return RenderTaskOutput(instruction=inp.task.instruction)
