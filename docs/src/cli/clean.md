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
