from pathlib import Path

from physics_lab.core.plugin_manager import PluginManager


def test_discovers_pendulum_plugin() -> None:
    manager = PluginManager(Path(__file__).parents[1] / "physics_lab" / "plugins")
    manager.discover()
    assert manager.get("pendulum").display_name == "单摆实验"
    assert manager.get("pendulum").device_requirements[0].device_type == "esp32s3_board"


def test_invalid_plugin_is_reported_without_blocking_discovery(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "broken"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text("value = 1\n", encoding="utf-8")

    manager = PluginManager(tmp_path)
    manager.discover()

    assert not manager.all()
    assert manager.issues[0].plugin_directory == "broken"
    assert "get_plugin" in manager.issues[0].message


def test_incompatible_and_duplicate_plugins_are_reported(tmp_path: Path) -> None:
    plugin_code = """
class Plugin:
    plugin_id = 'same'
    api_version = 1
    version = '1.0.0'
    display_name = 'Same'
    description = 'test'
    icon = '*'
    device_requirements = ()
    def create_workflow(self, project, services):
        return None
def get_plugin():
    return Plugin()
"""
    first = tmp_path / "a_first"
    second = tmp_path / "b_duplicate"
    incompatible = tmp_path / "c_incompatible"
    for directory in (first, second, incompatible):
        directory.mkdir()
    (first / "plugin.py").write_text(plugin_code, encoding="utf-8")
    (second / "plugin.py").write_text(plugin_code, encoding="utf-8")
    (incompatible / "plugin.py").write_text(plugin_code.replace("api_version = 1", "api_version = 99"), encoding="utf-8")

    manager = PluginManager(tmp_path)
    manager.discover()

    assert list(manager.plugins) == ["same"]
    assert len(manager.issues) == 2
    assert any("Duplicate plugin id" in issue.message for issue in manager.issues)
    assert any("supports v1" in issue.message for issue in manager.issues)
