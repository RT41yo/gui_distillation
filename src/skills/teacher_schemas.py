from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


# --- Canonical ID mappings ---
SYMBOL_ID_MAP = {
    "÷": "divide",
    "/": "divide",
    "×": "multiply",
    "*": "multiply",
    "+": "plus",
    "−": "minus",
    "-": "minus",
    "=": "equals",
    ".": "decimal",
}

DIGIT_ID_MAP = {str(i): f"digit_{i}" for i in range(10)}

ALIAS_ID_MAP = {
    "backspace": "backspace",
    "bksp": "backspace",
    "clear": "backspace",
    "display": "display",
}


def canonicalize_element_id(raw_id: str, raw_text: Optional[str]) -> str:
    rid = (raw_id or "").strip()
    if not rid:
        return rid

    if rid in SYMBOL_ID_MAP:
        return SYMBOL_ID_MAP[rid]

    if rid in DIGIT_ID_MAP:
        return DIGIT_ID_MAP[rid]

    low = rid.lower()
    if low in ALIAS_ID_MAP:
        return ALIAS_ID_MAP[low]

    if raw_text:
        t = raw_text.strip()
        if t in SYMBOL_ID_MAP:
            return SYMBOL_ID_MAP[t]
        if t in DIGIT_ID_MAP:
            return DIGIT_ID_MAP[t]

    return rid


class ScreenInfo(BaseModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class UIElement(BaseModel):
    id: str = Field(min_length=1)
    type: Literal["button", "text_field"] = "button"
    text: Optional[str] = None
    supported_actions: List[Literal["click"]] = Field(default_factory=lambda: ["click"])
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

    @model_validator(mode="after")
    def _canonicalize(self) -> "UIElement":
        self.id = canonicalize_element_id(self.id, self.text)

        # disallow symbol ids after canonicalization
        if self.id in SYMBOL_ID_MAP.keys():
            raise ValueError(f"Element id must not be a symbol: {self.id}")

        return self


class ObservationResponse(BaseModel):
    screen: ScreenInfo
    elements: List[UIElement] = Field(default_factory=list)
    notes: Optional[str] = None


class ActionParameters(BaseModel):
    button: Optional[Literal["left"]] = "left"
    clicks: Optional[int] = Field(default=1, ge=1, le=3)
    text: Optional[str] = None
    key: Optional[str] = None
    keys: Optional[List[str]] = None
    duration: Optional[float] = Field(default=None, ge=0.0)


class ActionProposal(BaseModel):
    action_type: Literal["click", "type", "press", "hotkey", "move_to"] = "click"
    coordinates: Optional[Tuple[int, int]] = None
    target_element_id: Optional[str] = None
    parameters: ActionParameters = Field(default_factory=ActionParameters)
    rationale: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class DeltaResponse(BaseModel):
    success: bool
    change_type: Literal[
        "no_change",
        "text_updated",
        "result_updated",
        "error_shown",
        "ui_changed",
        "unknown",
    ] = "unknown"
    description: str = Field(min_length=1)
    ui_state_changed: bool = False
    content_state_changed: bool = False
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)

    before_text: Optional[str] = None
    after_text: Optional[str] = None
