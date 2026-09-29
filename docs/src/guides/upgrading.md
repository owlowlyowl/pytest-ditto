# Upgrading

## Upgrading to 2.0

pytest-ditto 2.0 changes the unmarked default from pickle to strict JSON and
removes pickle from the core distribution. Existing `.pkl` snapshots are
ignored by the JSON path: core does not inspect, load, compare, convert, or
migrate them.

When a `.json` snapshot is absent, a normal or update run follows ordinary
missing-snapshot behavior and records current test output as new JSON, even if
a same-key `.pkl` file exists. A read-only verification run reports the JSON key
as missing. Re-recording does not prove that the current output is equivalent
to the old baseline.

Use this upgrade workflow:

1. Upgrade and run the complete test suite to create missing JSON snapshots.
2. For strict-JSON failures, change the snapshotted representation or select a
   suitable installed recorder.
3. Review every new JSON snapshot. It was recorded from current output, not
   converted or compared with pickle.
4. Run the complete suite again.
5. Run `ditto lock` only after accepting the new baselines.
6. Remove old `.pkl` snapshots manually or through the ordinary prune workflow.

If pickle is deliberately required, install `pytest-ditto-pickle` and select
its recorder explicitly. Loading pickle data can execute arbitrary code, so
only load trusted snapshots. Core provides no pickle warning, guard, migration
command, or convenience extra.

`pytest-ditto-pickle` names its snapshot files after the recorder, so they end
in `.pickle`, not `.pkl`. A 1.x `.pkl` file must already be renamed to its 2.0
key to be found; give the renamed file the `.pickle` ending. If you used
`pytest-ditto-pickle` 2.0.0b1, which still wrote `.pkl`, rename those snapshots
to end in `.pickle` and run `ditto lock`.

Version 2.0 registers the pytest plugin under the name `ditto` instead of
`recording`, which collided with the `pytest-recording` plugin. To disable
pytest-ditto for a run, use `-p no:ditto` in place of `-p no:recording`.

Version 2.0 also removes `DittoTestCase`. Unittest-style classes collected by
pytest should use pytest fixtures and marks. Direct `Snapshot` construction is
the lower-level alternative when fixture injection is unsuitable.

A directly constructed `Snapshot` takes a single `mode` in place of the
`update` and `readonly` flags: `Snapshot(..., mode=SnapshotMode.UPDATE)` replaces
`update=True`, and `mode=SnapshotMode.VERIFY` replaces `readonly=True`. The
default, `SnapshotMode.RECORD`, matches the old defaults. Import `SnapshotMode`
from `ditto`. A `Snapshot` given a `recorder` also needs `recorder_name=`, the
name the recorder is registered under, which names its snapshot files:
`Snapshot(..., recorder=recorders.get("yaml"), recorder_name="yaml")`. Passing
one without the other raises `TypeError`. Omit both for strict JSON.

Recorders serialise to bytes: a `Recorder` is `Recorder(dumps=..., loads=...)`,
where `dumps` turns a value into the snapshot file's bytes and `loads` turns
them back. The path-based `Recorder(save=..., load=...)` is gone. A plugin still
built on it fails to load with a message saying so. Rebuild it on the
library's in-memory functions, or wrap its file functions with
`ditto.recorders.recorder_from_files`. See
[Custom Recorders](custom-recorders.md).

`snapshot()` now returns the value as the recorder reads it back on every run.
Before, the run that recorded or updated a snapshot, or verified a missing one,
returned the value passed in. A value the recorder doesn't store exactly used
to pass on that run and fail on the next one; it now fails straight away. For
example, the YAML recorder reads a tuple back as a list, so
`assert (1, 2) == snapshot((1, 2), key="pair")` under `@ditto.yaml` now fails
when first recorded. Snapshot a list instead, or use a recorder that keeps the
distinction. A recorder whose `loads` can't read the bytes its `dumps` produced
now raises before anything is written.

Under pytest-xdist distribution (`-n N`, or `--dist` with `--tx`),
`--ditto-verify`, `--ditto-lock`, `--ditto-prune` and `--ditto-prune-dry-run`
are now a usage error (exit code 4), raised before any test runs. Before,
verify passed without checking anything, prune only warned, and `--ditto-lock`
failed only after the whole suite had run under `-n`. Run these single-process,
after a parallel test run if you like. See
[Running under pytest-xdist](lock-file.md#running-under-pytest-xdist).

YAML and `pytest-ditto-pandas` CSV snapshots are now written with `"\n"` line
endings on every platform, as JSON already was. On Windows, snapshots those
recorders wrote before used `"\r\n"`. They still load; the next
`--ditto-update` rewrites them with `"\n"`, a one-time line-ending diff.

Git on Windows often converts line endings on checkout (`core.autocrlf`), which
gives a working copy with `"\r\n"` while ditto writes `"\n"`. Snapshots still
load, but to keep them byte-for-byte what ditto wrote, add this to your
repository's `.gitattributes`:

```gitattributes
# Snapshots are byte-exact: never convert their line endings.
**/.ditto/** -text
```

If snapshots live in a directory other than `.ditto`, for example one set with
`ditto_target`, add a line for that directory too.

## Snapshot Key Format Change

Recent versions changed how snapshot keys are derived. Snapshots recorded by
older versions will not be found after upgrading:

- **`file://` snapshots** are now stored as flat `module.group@key.ext` files
  (one `.ditto/` directory, no per-module subdirectories)
- **Class-based test keys** now include the class name
  (`TestClass.test_method` rather than `test_method`)
- **Snapshot keys** can't contain `@`, `/`, `\` or control characters;
  `snapshot()` raises `ValueError` for one. Rename such keys.
- **`file://` snapshot names are percent-encoded** where the test name or key
  holds `%`, `/` or a character Windows forbids in file names
  (`\ : * ? " < > |` or a control character), so `test_at[12:00]` is stored as
  `test_at[12%3A00]`. Before, a `/` in a parametrize ID put the snapshot in a
  subdirectory of `.ditto/`. Names without these characters are unchanged.

To keep the baselines of snapshots whose names are now encoded, rename them
before the first run. This script does it for every `.ditto/` directory under
the current one; adjust the glob if your snapshots live elsewhere:

```python
from pathlib import Path

UNSAFE = set('%<>:"/\\|?*') | {chr(c) for c in range(32)}


def encode(name):
    return "".join(f"%{ord(c):02X}" if c in UNSAFE else c for c in name)


for ditto_dir in [d for d in Path(".").rglob(".ditto") if d.is_dir()]:
    # Plan every rename first. One file's new name can be another file's
    # current name (`a:b` becomes `a%3Ab`, which itself becomes `a%253Ab`), so
    # every file moves to a temporary name before any takes its new one.
    plan = {}
    for path in [p for p in ditto_dir.rglob("*") if p.is_file()]:
        old = path.relative_to(ditto_dir).as_posix()
        if encode(old) != old:
            plan[path] = ditto_dir / encode(old)
    taken = [new for new in plan.values() if new.exists() and new not in plan]
    if taken:
        raise FileExistsError(f"not renaming anything; already exist: {taken}")
    staged = {}
    for i, (path, new) in enumerate(plan.items()):
        staged[path.rename(ditto_dir / f".ditto-rename-{i}.tmp")] = new
    for tmp, new in staged.items():
        tmp.rename(new)
```

It encodes the whole name, so it assumes your test file paths contain none of
these characters. Afterwards, remove any subdirectories it leaves empty.

## Migration Steps

Because a missing snapshot is **recorded and passes** rather than failing, an
upgrade will silently re-record every snapshot from your code's current output
on the next run.

To avoid masking a regression:

1. **Re-record deliberately** with `--ditto-update`:

    ```bash
    ditto update
    ```

2. **Review the regenerated snapshots** in your diff — do not trust the first
   green run after upgrading

3. **Commit** the updated snapshots once you're satisfied

## Migration from `ditto_backend`

If you previously used a `ditto_backend` fixture, migrate to the
`target=` + backend registration model:

1. Register a URI scheme under `ditto_backends`:

    ```toml
    [project.entry-points.ditto_backends]
    myscheme = "my_package:create_backend"
    ```

2. Move runtime auth and connection kwargs into `ditto_storage_options`:

    ```python
    @pytest.fixture(scope="session")
    def ditto_storage_options():
        return {"myscheme": {"password": os.environ["PASSWORD"]}}
    ```

3. Select the backend with `target=` or `ditto_target`:

    ```toml
    [tool.pytest.ini_options]
    ditto_target = "myscheme://host/db"
    ```
