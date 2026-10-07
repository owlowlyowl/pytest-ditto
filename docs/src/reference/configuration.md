# Configuration

Every setting pytest-ditto reads, in one place. The guides explain when to use
each one; this page lists exactly what each one accepts.

## Command-line options

pytest-ditto adds these options to `pytest`. The `ditto` commands that run
tests (`ditto update`, `ditto verify`, `ditto lock`, `ditto prune`) pass them
for you, and pass any other arguments through to pytest.

| Option | `ditto` command | Effect |
|---|---|---|
| `--ditto-update` | `ditto update` | Overwrite every snapshot the run reaches with the current value. A full, passing run also rebuilds `ditto.lock`. |
| `--ditto-verify` | `ditto verify` | Never write snapshots or the lock; fail the run if storage and `ditto.lock` disagree. |
| `--ditto-lock` | `ditto lock` | Rebuild `ditto.lock` from this run. Refused unless the run is full and passes. |
| `--ditto-prune` | `ditto prune` | After the run, delete stored snapshots that `ditto.lock` doesn't record. |
| `--ditto-prune-dry-run` | `ditto prune --check` | Report what `--ditto-prune` would delete, without deleting. |
| `--ditto-prune-shared` | `ditto prune --shared` | Let prune delete from a target other checkouts might share: any target other than a `file://` path inside the rootdir. |

Without any of them, a run records missing snapshots, returns stored ones, and
adds new snapshots to `ditto.lock`. See
[How Snapshots Work](../concepts/snapshots.md#record-update-and-verify) for the
modes and [The Lock File](../concepts/lock-file.md#how-it-is-produced-and-maintained)
for what each does to the lock.

These combinations are a usage error, raised before any test runs:

- `--ditto-verify` with `--ditto-update`, `--ditto-lock`, `--ditto-prune` or
  `--ditto-prune-dry-run`
- `--ditto-prune` with `--ditto-prune-dry-run`
- `--ditto-verify`, `--ditto-lock`, `--ditto-prune` or `--ditto-prune-dry-run`
  under pytest-xdist distribution; see
  [Running tests in parallel](../guides/ci.md#running-tests-in-parallel)

`--ditto-introspect PATH` is internal: the `ditto` inventory commands use it
for `--live`.

## ini options

Set these in any pytest configuration file (`pyproject.toml`, `pytest.ini`,
`tox.ini` or `setup.cfg`), or for one run with `-o`, such as
`pytest -o "ditto_target=s3://my-bucket/snapshots/"`.

| Option | Default | Effect |
|---|---|---|
| `ditto_target` | `file://.ditto` | The target URI for every test without its own `target=` or `target_profile=`. A relative `file://` path is resolved against each test file's directory. A URI containing a password or a secret query parameter stops the run. |
| `ditto_target_profile` | none | The name of a [target profile](#target-profiles) to use as the default target. |

Set at most one of the two; setting both stops the run. In `pyproject.toml`:

```toml
[tool.pytest.ini_options]
ditto_target = "s3://my-bucket/snapshots/"
```

## Marks

| Mark | Effect |
|---|---|
| `@ditto.record(name)` | Store this test's snapshots with the recorder registered as `name`. |
| `@ditto.record(name, target=uri)` | Also store them in the target `uri`. |
| `@ditto.record(name, target_profile=profile)` | Also store them in the target named by a [profile](#target-profiles). |
| `@ditto.json`, `@ditto.yaml`, `@ditto.<name>` | Shorthand for `@ditto.record("<name>")`. A dotted name `ns.fmt` is `@ditto.ns.fmt`. Each takes the same `target=` and `target_profile=` arguments. |

A mark can be set on a function, a class or a module (`pytestmark`). A test
may have only one `record` mark in total, and the recorder name is required
whenever a mark is used. `target=` and `target_profile=` can't both be given.

A test's target is the first of these that is set: the mark's `target=`, the
mark's `target_profile=`, `ditto_target`, `ditto_target_profile`, then
`file://.ditto`. See [Storage Backends](../guides/backends.md).

## Fixtures

pytest-ditto provides one fixture, and reads two that you can define.

### `snapshot`

The fixture your tests request. Call it as `snapshot(data, key)`; see
[How Snapshots Work](../concepts/snapshots.md).

### `ditto_storage_options`

Define it to pass credentials and connection settings to storage. It returns a
dictionary from URI scheme to the keyword arguments for that scheme's backend:

```python
# conftest.py
import os
import pytest


@pytest.fixture(scope="session")
def ditto_storage_options():
    return {"s3": {"key": os.environ["AWS_KEY"], "secret": os.environ["AWS_SECRET"]}}
```

It applies to targets given as a URI (`target=` or `ditto_target`), not to
profiles. Values must be hashable, apart from nested dictionaries, lists,
tuples and sets. See
[Credentials and connection settings](../guides/backends.md#credentials-and-connection-settings-ditto_storage_options).

### `ditto_target_profiles`

Define it to declare [target profiles](#target-profiles) whose values come from
the environment, such as secrets. It returns a dictionary from profile name to
profile.

## Target profiles

A profile is a named target. Define profiles in the `ditto_target_profiles`
fixture, or in `pyproject.toml`:

```toml
[tool.pytest-ditto.target_profiles]
golden = "s3://my-bucket/golden/"

[tool.pytest-ditto.target_profiles.s3_east]
uri = "s3://east-bucket/golden/"
storage_options = { endpoint_url = "https://s3.us-east-1.amazonaws.com" }
```

Each profile is either a URI string or a table with a `uri` string and an
optional `storage_options` table; any other key is an error. A profile's
`storage_options` replace `ditto_storage_options` for that target. A name
defined in both the fixture and `pyproject.toml` is an error, and so is
selecting a name that isn't defined.

The `[tool.pytest-ditto.target_profiles]` table is read only from the
`pyproject.toml` in pytest's rootdir. See
[Named profiles](../guides/backends.md#named-profiles).

## Entry-point groups

Packages extend pytest-ditto through these entry-point groups:

| Group | Entry-point name | Value |
|---|---|---|
| `ditto_recorders` | The recorder's name, such as `msgpack` or `myplugin.myformat` | A `Recorder` object; see [Writing a Recorder](../guides/custom-recorders.md) |
| `ditto_backends` | The URI scheme, such as `redis` | A backend factory; see [Writing a Backend](../guides/custom-backends.md) |

## Warnings and exit codes

pytest-ditto's advisory warnings use the `ditto.exceptions.DittoWarning`
category. Filter them as usual, for example:

```toml
[tool.pytest.ini_options]
filterwarnings = ["error::ditto.exceptions.DittoWarning"]
```

A run that fails because of ditto (drift found by `--ditto-verify`, a refused
or failed lock rebuild, a prune that couldn't finish) exits with pytest's
usual failure code, 1. A usage error, such as conflicting options, exits with
4 before any test runs.
