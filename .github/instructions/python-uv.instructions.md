---
description: 'Mandatory: all Python work must use uv and a .venv virtual environment'
applyTo: '**/*.py, **/*.ipynb'
---

# Python Environment Policy

## Mandatory Rules

* Never use `pip install` directly. Always use `uv add <package>`.
* Never run Python scripts or tools outside a virtual environment.
* Before any Python work, verify a `.venv` exists in the project root. If not, create one with `uv init` and `uv sync`.
* Always use `uv` for all package management: adding, removing, locking, and syncing dependencies.
* If a `requirements.txt` exists but no `pyproject.toml`, migrate it: run `uv init` then `uv add` the packages.
* Always use `.venv` as the virtual environment directory name.
* Default to Python 3.12 unless the project specifies otherwise.
