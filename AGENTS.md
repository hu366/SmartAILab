# Repository Guidelines

## Project Structure & Module Organization

- `app.py` is the desktop application entry point.
- `physics_lab/core/` contains shared contracts, plugin discovery, project persistence, and task or device abstractions.
- `physics_lab/ui/` contains the PySide6 main window, navigation, pages, and application styles.
- `physics_lab/plugins/<plugin_id>/` contains self-contained experiment plugins. A plugin may provide its own configuration, operation, result pages, controller, protocol, and Arduino firmware source.
- `tests/` contains pytest tests for core behavior. Local experiment projects are stored under `projects/` and should not be committed.

Keep platform code independent from experiment-specific logic. New experiments should be added as plugins rather than by branching the main window or core workflow code.

## Build, Test, and Development Commands

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the desktop application:

```powershell
python app.py
```

Run the test suite:

```powershell
python -m pytest -q
```

Run a syntax check:

```powershell
python -m compileall -q physics_lab tests app.py
```

## Coding Style & Naming Conventions

Use Python 3 type hints, four-space indentation, and concise comments only where behavior is non-obvious. Follow standard Python naming: `snake_case` for functions and variables, `PascalCase` for classes, and lowercase stable identifiers for plugin IDs. Keep Qt pages thin; place experiment logic in controllers or services rather than widgets.

## Testing Guidelines

Use pytest. Name test files `test_<area>.py` and test functions `test_<behavior>`. Cover plugin discovery, project save/load round trips, validation, and hardware protocol parsing. Use simulated devices or protocol fixtures so tests do not require physical hardware.

## Commit & Pull Request Guidelines

This repository has no Git history yet, so no established commit convention can be inferred. Use imperative, focused commit subjects such as `Add pendulum plugin` or `Validate project metadata`. Pull requests should explain the user-visible behavior, identify affected plugins or core interfaces, include test results, and attach screenshots for UI changes. Document any Arduino protocol or firmware compatibility changes.

## Architecture & Hardware Notes

Plugins may use different Arduino firmware and command protocols. Declare required device types and capabilities in `device_requirements`; use `PlatformServices.device_manager` to acquire devices. Keep serial or other transport code in shared device layers, and keep firmware-specific parsing and commands inside the corresponding plugin adapter. Manual Arduino flashing is expected; never assume the application can flash hardware automatically.
