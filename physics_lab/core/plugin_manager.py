from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path

from physics_lab.core.contracts import ExperimentPlugin

PLUGIN_API_VERSION = 1
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class PluginContractError(ValueError):
    """Raised when a discovered module does not implement the plugin contract."""


@dataclass(frozen=True)
class PluginLoadIssue:
    plugin_directory: str
    message: str


class PluginManager:
    def __init__(self, plugins_root: Path) -> None:
        self.plugins_root = plugins_root
        self.plugins: dict[str, ExperimentPlugin] = {}
        self.issues: list[PluginLoadIssue] = []

    def discover(self) -> None:
        self.plugins.clear()
        self.issues.clear()
        if not self.plugins_root.exists():
            return
        for plugin_file in sorted(self.plugins_root.glob("*/plugin.py")):
            try:
                plugin = self._load(plugin_file)
                if plugin.plugin_id in self.plugins:
                    raise PluginContractError(f"Duplicate plugin id: {plugin.plugin_id}")
                self.plugins[plugin.plugin_id] = plugin
            except Exception as exc:
                self.issues.append(PluginLoadIssue(plugin_file.parent.name, str(exc)))

    @staticmethod
    def _load(plugin_file: Path) -> ExperimentPlugin:
        module_name = f"physics_lab_dynamic_{plugin_file.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec is None or spec.loader is None:
            raise PluginContractError("Unable to create a module loader")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        get_plugin = getattr(module, "get_plugin", None)
        if not callable(get_plugin):
            raise PluginContractError(f"Plugin {plugin_file.parent.name} must define get_plugin()")
        plugin = get_plugin()
        PluginManager._validate(plugin, plugin_file.parent.name)
        return plugin

    @staticmethod
    def _validate(plugin: ExperimentPlugin, directory_name: str) -> None:
        required = ("plugin_id", "version", "display_name", "description", "icon")
        missing = [name for name in required if not getattr(plugin, name, None)]
        if missing:
            raise PluginContractError(
                f"Plugin {directory_name} is missing required metadata: {', '.join(missing)}"
            )
        if not isinstance(plugin.device_requirements, tuple):
            raise PluginContractError(f"Plugin {plugin.plugin_id} device_requirements must be a tuple")
        if any(not hasattr(requirement, "device_type") for requirement in plugin.device_requirements):
            raise PluginContractError(f"Plugin {plugin.plugin_id} has an invalid device requirement")
        if not callable(getattr(plugin, "create_workflow", None)):
            raise PluginContractError(f"Plugin {plugin.plugin_id} must define create_workflow()")
        api_version = getattr(plugin, "api_version", PLUGIN_API_VERSION)
        if api_version != PLUGIN_API_VERSION:
            raise PluginContractError(
                f"Plugin {plugin.plugin_id} requires API v{api_version}; "
                f"platform supports v{PLUGIN_API_VERSION}"
            )
        if not VERSION_PATTERN.fullmatch(str(plugin.version)):
            raise PluginContractError(f"Plugin {plugin.plugin_id} has invalid version: {plugin.version}")

    def all(self) -> list[ExperimentPlugin]:
        return list(self.plugins.values())

    def get(self, plugin_id: str) -> ExperimentPlugin:
        return self.plugins[plugin_id]
