"""
MCP-style executor tools: click, type_text, hotkey, scroll, wait.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.executor.pyautogui_adapter import PyAutoGUIAdapter


@dataclass
class ClickInput:
    x: float
    y: float
    button: str = "left"


class ClickTool:
    def __init__(self, adapter: PyAutoGUIAdapter) -> None:
        self._adapter = adapter

    def run(self, inp: ClickInput) -> None:
        self._adapter.click(inp.x, inp.y, inp.button)


# ---------------------------------------------------------------------------

@dataclass
class TypeTextInput:
    text: str
    interval: float = 0.05


class TypeTextTool:
    def __init__(self, adapter: PyAutoGUIAdapter) -> None:
        self._adapter = adapter

    def run(self, inp: TypeTextInput) -> None:
        self._adapter.type_text(inp.text, inp.interval)


# ---------------------------------------------------------------------------

@dataclass
class HotkeyInput:
    keys: List[str]


class HotkeyTool:
    def __init__(self, adapter: PyAutoGUIAdapter) -> None:
        self._adapter = adapter

    def run(self, inp: HotkeyInput) -> None:
        self._adapter.hotkey(inp.keys)


# ---------------------------------------------------------------------------

@dataclass
class ScrollInput:
    x: float
    y: float
    direction: str = "down"
    amount: int = 3


class ScrollTool:
    def __init__(self, adapter: PyAutoGUIAdapter) -> None:
        self._adapter = adapter

    def run(self, inp: ScrollInput) -> None:
        self._adapter.scroll(inp.x, inp.y, inp.direction, inp.amount)


# ---------------------------------------------------------------------------

@dataclass
class WaitInput:
    duration: float = 1.0


class WaitTool:
    def __init__(self, adapter: PyAutoGUIAdapter) -> None:
        self._adapter = adapter

    def run(self, inp: WaitInput) -> None:
        self._adapter.wait(inp.duration)
