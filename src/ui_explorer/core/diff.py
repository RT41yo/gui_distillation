from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ui_explorer.core.state import StateSignature
from ui_explorer.execution.executor import ExecutionResult


class TransitionKind(str, Enum):
    NEW_MACRO_STATE = "new_macro_state"
    SAME_STATE = "same_state"
    CONTENT_CHANGED = "content_changed"
    FAILED_CLICK = "failed_click"


@dataclass(frozen=True)
class TransitionResult:
    kind: TransitionKind
    to_state: str | None
    macro_changed: bool
    content_changed: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "to_state": self.to_state,
            "macro_changed": self.macro_changed,
            "content_changed": self.content_changed,
            "reason": self.reason,
        }


class DiffClassifier:
    def classify(
        self,
        before: StateSignature,
        after: StateSignature,
        execution: ExecutionResult,
    ) -> TransitionResult:
        if not execution.ok:
            return TransitionResult(
                kind=TransitionKind.FAILED_CLICK,
                to_state=None,
                macro_changed=False,
                content_changed=False,
                reason=execution.error or "execution failed",
            )

        macro_changed = before.macro_hash != after.macro_hash
        content_changed = before.content_hash != after.content_hash

        if macro_changed:
            return TransitionResult(
                kind=TransitionKind.NEW_MACRO_STATE,
                to_state=after.state_id,
                macro_changed=True,
                content_changed=content_changed,
                reason="macro signature changed",
            )

        if content_changed:
            return TransitionResult(
                kind=TransitionKind.CONTENT_CHANGED,
                to_state=before.state_id,
                macro_changed=False,
                content_changed=True,
                reason="content signature changed, macro signature unchanged",
            )

        return TransitionResult(
            kind=TransitionKind.SAME_STATE,
            to_state=before.state_id,
            macro_changed=False,
            content_changed=False,
            reason="no A11Y signature change after action",
        )
