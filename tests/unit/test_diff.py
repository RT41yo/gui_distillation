from ui_explorer.core.diff import DiffClassifier, TransitionKind
from ui_explorer.execution.executor import ExecutionResult


class Sig:
    def __init__(self, state_id: str, macro_hash: str, content_hash: str):
        self.state_id = state_id
        self.macro_hash = macro_hash
        self.content_hash = content_hash


def test_diff_classifies_macro_change():
    result = DiffClassifier().classify(
        before=Sig("a", "m1", "c1"),
        after=Sig("b", "m2", "c2"),
        execution=ExecutionResult(ok=True, method="test"),
    )

    assert result.kind == TransitionKind.NEW_MACRO_STATE
    assert result.to_state == "b"


def test_diff_classifies_content_change():
    result = DiffClassifier().classify(
        before=Sig("a", "m1", "c1"),
        after=Sig("a", "m1", "c2"),
        execution=ExecutionResult(ok=True, method="test"),
    )

    assert result.kind == TransitionKind.CONTENT_CHANGED
    assert result.to_state == "a"


def test_diff_classifies_failed_click():
    result = DiffClassifier().classify(
        before=Sig("a", "m1", "c1"),
        after=Sig("a", "m1", "c1"),
        execution=ExecutionResult(ok=False, method="test", error="boom"),
    )

    assert result.kind == TransitionKind.FAILED_CLICK
    assert result.to_state is None
