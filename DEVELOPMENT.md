# Development

## Prerequisites

- [pixi](https://pixi.sh/) (v0.69+) — environment and task management
- [Docker](https://www.docker.com/) — only for running backend examples (PostgreSQL, Redis)

## Setup

Clone the repository and install the default environment:

```bash
git clone https://github.com/owlowlyowl/pytest-ditto.git
cd pytest-ditto
pixi install
```

The package is installed in editable mode automatically via the workspace config.

## Environments

pixi manages multiple isolated environments for different tasks:

| Environment | Purpose | Key dependencies |
|-------------|---------|------------------|
| `default` | Basic development | pytest-ditto (editable) |
| `py312` | Test on Python 3.12 | pytest, pytest-cov, hypothesis |
| `py313` | Test on Python 3.13 | pytest, pytest-cov, hypothesis |
| `py314` | Test on Python 3.14 | pytest, pytest-cov, hypothesis |
| `pandas` | Test with pandas recorders | pytest-ditto-pandas |
| `pyarrow` | Test with PyArrow recorders | pytest-ditto-pyarrow |
| `lint` | Linting and type checking | pre-commit, ruff, basedpyright |
| `docs` | Documentation | zensical, mkdocstrings-python |
| `build` | Package building | uv |
| `examples` | Run backend examples | duckdb, redis, psycopg2 |

Install a specific environment:

```bash
pixi install -e py312
pixi install -e lint
```

## Testing

Run tests on a specific Python version:

```bash
pixi run -e py312 test
pixi run -e py313 test
pixi run -e py314 test
```

With coverage:

```bash
pixi run -e py312 test-cov
```

Coverage reports are generated in HTML, terminal, and XML formats.

### Plugin tests

First-party recorder plugins live under `plugins/<name>/`, each a separate
distribution with its own `pyproject.toml`, tests, `ditto.lock` and snapshots.
The `<name>-py312`/`py313`/`py314` environments install the plugin from
`plugins/<name>` as an editable path dependency next to core, and its tasks run
from the plugin's directory, the way a third-party plugin's suite runs:

```bash
pixi run -e pyarrow-py312 test-pyarrow     # PyArrow plugin tests
pixi run -e pyarrow-py312 verify-pyarrow   # its snapshots against its ditto.lock
```

The core environments (`default`, `py312`–`py314`) never install a plugin.
Plugins share core's version, computed from the same git tag.

The pandas plugin has not moved in yet:

```bash
pixi run -e pandas test       # core suite with pytest-ditto-pandas 0.1.0
```

## Linting & Type Checking

Run all linters (ruff check, ruff format, basedpyright) via pre-commit:

```bash
pixi run -e lint lint
```

Run the type checker standalone:

```bash
pixi run -e lint typecheck
```

### Pre-commit hooks

The project uses pre-commit with local hooks that run through pixi. The hooks are:

1. **ruff** — linting with auto-fix (`src/` and `tests/`)
2. **ruff-format** — code formatting (`src/` and `tests/`)
3. **basedpyright** — type checking (`src/`)

Install pre-commit hooks for automatic checks on commit:

```bash
pixi run -e lint pre-commit install
```

## Documentation

Preview the documentation site locally:

```bash
pixi run -e docs docs-serve
```

This starts a live-reload server at `http://localhost:8000`.

Build the static site:

```bash
pixi run -e docs docs-build
```

Output goes to `docs/site/` (gitignored).

The documentation is built with [Zensical](https://zensical.org/) and uses
[mkdocstrings](https://mkdocstrings.github.io/) for API reference generation
from docstrings.

### Documentation structure

```
docs/
├── mkdocs.yml        # Zensical configuration
└── src/              # Markdown source files
    ├── index.md
    ├── getting-started.md
    ├── guides/       # Prose guides
    ├── cli/          # CLI reference
    ├── reference/    # API reference (auto-generated)
    └── img/          # Screenshots
```

## Building

Build the sdist and wheel:

```bash
pixi run -e build build
```

Output goes to `dist/`. The package uses [hatch](https://hatch.pypa.io/) with
[hatch-vcs](https://github.com/ofek/hatch-vcs) for version management from git tags.

## Examples

Self-contained examples demonstrating different backends:

### Local (file-based)

```bash
pixi run -e examples examples-local
```

### DuckDB

```bash
pixi run -e examples examples-duckdb
```

Reset the DuckDB database:

```bash
pixi run -e examples examples-duckdb-reset
```

### PostgreSQL (requires Docker)

```bash
pixi run -e examples examples-postgres-up      # start container
pixi run -e examples examples-postgres         # run examples
pixi run -e examples examples-postgres-down    # stop container
pixi run -e examples examples-postgres-reset   # remove container + volume
```

### Redis (requires Docker)

```bash
pixi run -e examples examples-redis-up         # start container
pixi run -e examples examples-redis            # run examples
pixi run -e examples examples-redis-down       # stop container
pixi run -e examples examples-redis-reset      # remove container + volume
```

## CI

GitHub Actions runs tests on Python 3.12, 3.13, and 3.14 on every push to
`main` and on pull requests. See `.github/workflows/ci.yml`.

Documentation is built and deployed to GitHub Pages on push to `main`.
See `.github/workflows/docs.yml`.

## Project Layout

```
├── src/ditto/            # Package source
│   ├── __init__.py       # Public API exports
│   ├── plugin.py         # pytest plugin hooks
│   ├── snapshot.py       # Snapshot fixture implementation
│   ├── cli.py            # CLI commands (click)
│   ├── recorders/        # Built-in recorders (pickle, yaml, json)
│   ├── backends/         # Storage backends (fsspec, transforms)
│   └── exceptions.py     # Exception hierarchy
├── tests/ci/             # Test suite
├── examples/             # Backend examples (local, postgres, redis, duckdb)
├── docs/                 # Documentation source
├── pyproject.toml        # Package metadata + pixi config
└── .github/workflows/    # CI workflows
```
