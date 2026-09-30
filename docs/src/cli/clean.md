# ditto clean

Deletes all `.ditto/` directories under a path. Shows a preview and asks for
confirmation unless `--yes` is passed.

## Usage

```
ditto clean [PATH] [--yes]
```

## Examples

```bash
# Clean with confirmation prompt
ditto clean

# Clean without confirmation
ditto clean --yes

# Clean a specific directory
ditto clean tests/ci/ --yes
```

## Screenshot

![ditto clean](../img/ditto-clean.png)

## Behaviour

- Finds all `.ditto/` directories under the given path
- Shows a preview of what will be deleted
- Asks for confirmation (unless `--yes` is passed)
- Deletes the directories

!!! note
    `ditto clean` is local-only and never touches remote snapshots.

Nested `.ditto/` directories are removed with their parent and are not scheduled
twice. PATH can be a `.ditto/` directory itself. Directory symlinks are not
followed for cleanup; an explicitly selected symlink is rejected. Filesystem
failures are reported on stderr with a non-zero exit status.
