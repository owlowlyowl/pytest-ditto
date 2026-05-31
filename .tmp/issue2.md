### Summary

`ditto list`, `status`, `stats`, and `lint` unconditionally spawn an internal `pytest --setup-only --ditto-introspect` subprocess (`src/ditto/cli.py:98`, `src/ditto/_cli_introspect.py`) to enumerate snapshots.

### Cost

- **Local-only projects pay a full pytest-startup cost** just to list files in `.ditto/` — slower than a directory walk for no benefit.
- **Remote backends require live credentials** merely to render an inventory: the pass imports test modules and resolves `ditto_target_profiles` / `ditto_storage_options` fixtures to open each backend.
- It imports your test modules as a side effect of a read-only reporting command.

### Context

`design-cli-remote-backends.md` actually specifies a *hybrid* (fast local filesystem path; introspection pass only for non-local/fixture-defined targets), but the implemented `_inventory_or_exit` "always introspects" — the fast path was never wired in. The justification for "always introspect" is that per-test `record(target=...)` marks are invisible to static config inspection.

### Desired outcome

Read-only inventory commands should have a fast, credential-free, remote-capable data source, with the live pytest pass becoming opt-in rather than mandatory.
