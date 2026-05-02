from ui_explorer.execution.executor import ActionExecutor


def test_executor_rejects_invalid_bbox():
    result = ActionExecutor(display=":99").click_bbox([-1, -1, 0, 0])

    assert result.ok is False
    assert result.method == "bbox_click"
    assert result.error is not None
