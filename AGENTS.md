# Repository Guidelines

## Project Structure & Module Organization

- `app.py` starts the PySide6 desktop application.
- `physics_lab/core/` contains contracts, plugin discovery, project persistence, cancellation, logging, device leasing, and simulated devices.
- `physics_lab/devices/` contains shared transports and real-device adapters.
- `physics_lab/ui/` contains the main window, workflow shell, raw-data panel, log dialog, and styles.
- `physics_lab/plugins/<plugin_id>/` contains self-contained experiment pages, controllers/protocols, result/export logic, and optional `firmware/` Arduino sources. Current plugins are `pendulum` and `temperature`.
- `tests/` contains pytest tests. `projects/` and `projects-test/` are generated local project data and are ignored by Git.

Keep platform code independent from experiment-specific logic. Add experiments as plugins, never by branching the main window or core workflow.

## Plugin and Workflow Contract

`plugin.py` must expose `get_plugin()` returning an object with `api_version`, `plugin_id`, `version`, `display_name`, `description`, `icon`, `device_requirements`, and `create_workflow(project, services)`. A workflow implements `page_ids()`, `page_title()`, `create_page()`, and `run(worker)`. Input pages implement `validate()` and `save_to_project(project)` where needed. Plugins own configuration, acquisition, results, and exports.

## Build, Test, and Development Commands

```powershell
python -m pip install -r requirements.txt
python app.py
python -m pytest -q
python -m compileall -q physics_lab tests app.py
```

Tests cover discovery, persistence, validation, logging, devices, and serial parsing; no coverage threshold is enforced.

## Coding Style & Naming Conventions

Use Python 3 type hints, four-space indentation, concise comments, `snake_case` functions/variables, `PascalCase` classes, and lowercase stable plugin IDs. Keep Qt pages thin; put experiment logic in controllers/services.

## Hardware, Data, and Logging

Model a physical device as one ESP32/Arduino control board with multiple sensor channels. Declare required board type, capabilities, firmware, and channels in `device_requirements`; acquire through `PlatformServices.device_manager` (use `acquire_all()` only when multiple boards are required). Use `PHYSICS_LAB_PENDULUM_PORT` for startup serial configuration. Keep shared serial transport in `physics_lab/devices/` and firmware-specific commands/parsing in the plugin adapter. Manual Arduino IDE flashing is expected; the app must not flash firmware automatically. Projects save `manifest.json`, plugin-defined JSONL under `raw/`, and optional `processed/`, `results/`, and `logs/` directories. CSV export is generic by default; plugins may customize it. Per-project logs are `logs/experiment.log` and `logs/errors.log`.

## Testing and Collaboration

Name tests `test_<area>.py` and functions `test_<behavior>`. Prefer simulated devices or protocol fixtures; hardware is optional. Use focused imperative commits such as `Add pendulum plugin`. Pull requests should describe user-visible behavior, affected plugins/interfaces, test results, and screenshots for UI changes, and document Arduino protocol or firmware compatibility changes. The repository tracks `main` with remote `origin` at `git@github.com:hu366/SmartAILab.git`.
