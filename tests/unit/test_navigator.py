from ui_explorer.execution.navigator import NavigationResult


def test_navigation_result_to_dict():
    result = NavigationResult(
        ok=True,
        target_state="root",
        actual_state="root",
        attempts=1,
        reason="root reached",
        xml_path="x.xml",
    )

    data = result.to_dict()

    assert data["ok"] is True
    assert data["target_state"] == "root"
    assert data["actual_state"] == "root"
    assert data["attempts"] == 1
