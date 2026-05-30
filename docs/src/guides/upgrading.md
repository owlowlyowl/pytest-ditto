# Upgrading

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
