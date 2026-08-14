# Experiment Plugin Template

Use this structure for a new experiment. Keep all experiment-specific pages, calculations, device protocols, and firmware under the plugin directory.

```text
plugins/<plugin_id>/
  __init__.py
  plugin.py
  config_page.py
  operation_page.py
  result_page.py
  controller.py
  protocol.py
  firmware/
```

`plugin.py` must expose `get_plugin()` and return an object with:

```python
plugin_id = "my_experiment"
api_version = 1
version = "1.0.0"
display_name = "My Experiment"
description = "Short description"
icon = "*"
device_requirements = (
    # Add one entry for each distinct device required by the experiment.
    # DeviceRequirement("sensor", frozenset({"sample"})),
)

def create_workflow(project, services):
    ...
```

Workflow pages should provide `validate() -> tuple[bool, str]` when they have user input and `save_to_project(project)` to persist plugin configuration. The platform calls both methods before moving to the next page. Do not call the main window directly from a plugin.
