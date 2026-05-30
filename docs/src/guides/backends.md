# Storage Backends

By default, snapshots are stored in a `.ditto/` directory next to each test
file. The storage target can be overridden at several levels.

## Priority Order

From highest to lowest priority:

```
mark target= → mark target_profile= → ditto_target ini → ditto_target_profile ini → file://.ditto
```

## Per-test: `target=`

Specify a URI directly in the mark:

```python
import ditto

# Local path relative to this test file
@ditto.record("json", target="file://snapshots/group_a")
def test_foo(snapshot): ...

# S3 bucket
@ditto.record("yaml", target="s3://my-bucket/ci-snapshots/")
def test_bar(snapshot): ...

# In-memory (ephemeral, no disk I/O)
@ditto.record("pickle", target="memory://")
def test_baz(snapshot): ...

# Registered non-fsspec backend
@ditto.record("json", target="postgresql://db-host/mydb")
def test_qux(snapshot): ...
```

`target=` accepts any URI whose scheme is:

- A supported [fsspec](https://filesystem-spec.readthedocs.io/) protocol
  (file, s3, gcs, memory, etc.)
- A scheme registered via the `ditto_backends` entry-point group

Relative `file://` paths resolve relative to the test file's directory.

## Authentication: `ditto_storage_options`

Credentials for remote backends belong in `conftest.py`, not in marks:

```python
# conftest.py
import os
import pytest


@pytest.fixture(scope="session")
def ditto_storage_options():
    return {
        "s3": {"key": os.environ["AWS_KEY"], "secret": os.environ["AWS_SECRET"]},
        "postgresql": {"password": os.environ["PGPASSWORD"]},
        "redis": {"password": os.environ["REDIS_PASSWORD"]},
    }
```

Values are passed as kwargs to `fsspec.core.url_to_fs` for fsspec schemes,
or to the registered backend factory for custom schemes.

## Project-wide: `ditto_target` ini

Set a default target for all tests in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
ditto_target = "s3://my-bucket/snapshots/"
```

Individual `target=` marks take precedence over this setting.

## Named Profiles: `target_profile=`

Profiles are reusable, named targets. Useful when:

- A suite routes to a small set of stable backends
- Two targets share a scheme but need different credentials

### Defining Profiles

In a fixture (dynamic, with secrets):

```python
# conftest.py
import os
import pytest


@pytest.fixture(scope="session")
def ditto_target_profiles():
    return {
        "golden": "s3://my-bucket/golden/",
        "s3_east": {
            "uri": "s3://east-bucket/golden/",
            "storage_options": {
                "key": os.environ["AWS_KEY"],
                "secret": os.environ["AWS_SECRET"],
            },
        },
    }
```

In `pyproject.toml` (static):

```toml
[tool.pytest-ditto.target_profiles]
golden = "s3://my-bucket/golden/"

[tool.pytest-ditto.target_profiles.s3_east]
uri = "s3://east-bucket/golden/"
storage_options = { key = "...", secret = "..." }
```

### Using Profiles

Per-test:

```python
import ditto

@ditto.record("json", target_profile="s3_east")
def test_foo(snapshot): ...
```

Project-wide:

```toml
[tool.pytest.ini_options]
ditto_target_profile = "golden"
```

### Profile Rules

- A profile value is either a URI string or a mapping with `uri` and optional
  `storage_options`
- Profiles **do not** read `ditto_storage_options` — they are self-contained
- `target=` and `target_profile=` are mutually exclusive on a mark
- `ditto_target` and `ditto_target_profile` are mutually exclusive in ini
- A name defined in both fixture and `pyproject.toml` raises an error
