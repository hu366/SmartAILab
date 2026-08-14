from types import SimpleNamespace

from physics_lab.ui.main_window import MainWindow


def make_window(thread, run_terminal: bool = False) -> MainWindow:
    window = MainWindow.__new__(MainWindow)
    window.current_workflow = SimpleNamespace(thread=thread, run_terminal=run_terminal)
    return window


def test_navigation_guard_detects_active_workflow_thread() -> None:
    assert make_window(object())._has_active_run()
    assert not make_window(None)._has_active_run()
    assert not make_window(object(), run_terminal=True)._has_active_run()
