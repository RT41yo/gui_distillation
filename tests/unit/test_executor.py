from ui_explorer.execution.executor import ActionExecutor


def test_executor_rejects_invalid_bbox():
    result = ActionExecutor(display=":99").click_bbox([-1, -1, 0, 0])

    assert result.ok is False
    assert result.method == "bbox_click"
    assert result.error is not None


def test_executor_result_contains_activation_flag():
    result = ActionExecutor(display=":99").click_bbox([-1, -1, 0, 0])

    data = result.to_dict()

    assert "activated" in data
