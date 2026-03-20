# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`pytest-ditto` is a pytest plugin for snapshot/regression testing. On the first test run, snapshot data is saved to disk; on subsequent runs, the stored data is returned for comparison.

## Commands

**Run tests:**
```bash
pixi run -e py312 test  # run full CI test suite on Python 3.12 (primary)
pixi run -e py314 test  # run full CI test suite on Python 3.14
pytest tests/ci/        # run the main CI test suite directly
pytest tests/ci/test_snapshot.py  # run a single test file
pytest tests/ci/test_snapshot.py::test_name  # run a single test
```

**Lint and format:**
```bash
pixi run -e lint lint   # run pre-commit (includes ruff) via pixi
```

**Build:**
```bash
pixi run -e build build  # builds sdist and wheel via uv
```

## Architecture

The plugin follows a layered design:

```
pytest plugin entry point (plugin.py → recording())
    ↓ provides `snapshot` fixture
Snapshot class (snapshot.py)
    ↓ delegates persistence to
IO Registry (io/__init__.py) + Plugin System (io/_plugins.py)
    ├── Built-in: Pickle (_pickle.py), YAML (_yaml.py), JSON (_json.py)
    └── External plugins via entry points (e.g. pytest-ditto-pandas, pytest-ditto-pyarrow)
```

**Key modules:**

- `src/ditto/plugin.py` — Registers the `snapshot` fixture and pytest marks; discovers IO format from test marks
- `src/ditto/snapshot.py` — `Snapshot` class; manages file paths (`{test_dir}/.ditto/{test_name}@{key}.{ext}`), `save()`/`load()` lifecycle
- `src/ditto/marks.py` — Exports `@ditto.pickle`, `@ditto.yaml`, `@ditto.json`; dynamically loads marks from `ditto_marks` entry point group
- `src/ditto/io/` — Persistence layer; `_protocol.py` defines the `Base` protocol (`save`/`load`); `_plugins.py` discovers external IO plugins via `ditto` entry point group
- `src/ditto/_unittest.py` — `DittoTestCase` for unittest.TestCase integration

**Snapshot file location:** `.ditto/` directories adjacent to test files (gitignored).

**Entry points (pyproject.toml):**
- `pytest11`: `ditto.plugin:recording` — registers the plugin with pytest
- `ditto`: built-in IO implementations (pickle, yaml, json)
- `ditto_marks`: built-in and external format marks

**Plugin extensibility:** External packages (e.g. `pytest-ditto-pandas`) register new IO formats and marks by declaring their own `ditto` and `ditto_marks` entry points.

**Test structure:** `tests/ci/` is the primary test suite run in CI. Other test directories (`fixture_scoped_*`, `multiple_snapshot_tests`, `nested_tests`) test specific fixture scoping and usage patterns.
