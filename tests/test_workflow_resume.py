from types import SimpleNamespace

from physics_lab.ui.main_window import WorkflowPage


def make_page(current_step: str, status: str = "draft") -> WorkflowPage:
    page = WorkflowPage.__new__(WorkflowPage)
    page.page_ids = ["plugin-config", "run", "result"]
    page.project = SimpleNamespace(current_step=current_step, status=status)
    return page


def test_workflow_restores_saved_step() -> None:
    assert make_page("run")._initial_page_index() == 1
    assert make_page("result", "completed")._initial_page_index() == 2


def test_workflow_falls_back_to_first_page_for_unknown_step() -> None:
    assert make_page("old-page", "draft")._initial_page_index() == 0
