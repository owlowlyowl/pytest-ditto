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

Version 2.0 also removes `DittoTestCase`. Unittest-style classes collected by
pytest should use pytest fixtures and marks. Direct `Snapshot` construction is
the lower-level alternative when fixture injection is unsuitable.

## Snapshot Key Format Change

Recent versions changed how snapshot keys are derived. Snapshots recorded by
older versions will not be found after upgrading:

- **`file://` snapshots** are now stored as flat `module.group@key.ext` files
  (one `.ditto/` directory, no per-module subdirectories)
- **Class-based test keys** now include the class name
  (`TestClass.test_method` rather than `test_method`)

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
