# Repository Guidelines

## Project Structure & Module Organization

- `app.py` starts the PySide6 application.
- `physics_lab/core/` contains contracts, discovery, persistence, cancellation, logging, leasing, and simulators; `physics_lab/devices/` contains serial transport, protocol validation, and real adapters.
- `physics_lab/ui/` contains the main window, workflow shell, raw-data panel, log dialog, and styles.
- `physics_lab/plugins/<plugin_id>/` contains experiment pages, logic, exports, and optional Arduino `firmware/`. Plugins: `pendulum`, `temperature`.
- `tests/` contains pytest tests; `projects/` and `projects-test/` are generated and ignored. Plugin docs: `PLUGIN_DEVELOPMENT.md`, `physics_lab/plugins/PLUGIN_TEMPLATE.md`.

Keep platform code independent from experiment-specific logic. Add experiments as plugins, never by branching the main window or core workflow.

## Plugin and Workflow Contract

`plugin.py` must expose `get_plugin()` with `api_version`, `plugin_id`, `version`, `display_name`, `description`, `icon`, `device_requirements`, and `create_workflow(project, services)`. Workflows implement `page_ids()`, `page_title()`, `create_page()`, and `run(worker)`; input pages implement `validate()` and `save_to_project(project)`. Plugins own logic; Qt pages do not call `MainWindow`.

## Build, Test, and Development Commands

```powershell
python -m pip install -r requirements.txt
python app.py
python -m pytest -q
python -m compileall -q physics_lab tests app.py
```

No coverage threshold is enforced.

## Coding Style & Naming Conventions

Use Python 3 type hints, four-space indentation, concise comments, `snake_case` functions/variables, `PascalCase` classes, and lowercase stable plugin IDs. Keep Qt pages thin; put experiment logic in controllers/services.

## Hardware, Data, and Logging

One ESP32/Arduino board may provide multiple channels. Declare board type, capabilities, firmware, and channels in `device_requirements`; acquire via `PlatformServices.device_manager` (use `acquire_all()` only for multiple boards) and release in `finally`. Use `PHYSICS_LAB_PENDULUM_PORT` or `PHYSICS_LAB_TEMPERATURE_PORT`; absent ports use simulators. Shared transport and protocol validation are in `physics_lab/devices/`; plugin parsing is in adapters. JSONL is `physics-lab-jsonl` v1; require `hello` and reject unsupported versions. Arduino sources stay in plugin `firmware/`; flashing is manual. Projects contain `manifest.json` with `schema_version`, plugin JSONL in `raw/`, optional `processed/`, `results/`, `logs/`, and experiment/error logs. Migrate old manifests; confirmed deletion removes the project directory. CSV is generic unless customized.

## Workflow Safety and Persistence

Disable navigation while a worker runs; window close must stop active work before Qt objects are destroyed. Resume history from `current_step`, keep project state in the repository, and ensure result `refresh()` updates summaries and raw-data views.

## Testing and Collaboration

Name tests `test_<area>.py` and functions `test_<behavior>`. Prefer simulators or protocol fixtures; hardware is optional. Tests cover core workflows, leasing, and protocol parsing; coverage: none. Use commits such as `Add pendulum plugin`. PRs describe behavior, interfaces, tests, screenshots, and Arduino compatibility. `main` tracks `origin` at `git@github.com:hu366/SmartAILab.git`.
