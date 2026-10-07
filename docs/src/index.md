# pytest-ditto

Snapshot testing with minimal ceremony and flexible recorders.

<div class="grid cards" markdown>

- :material-camera: **Snapshot Testing**

    Record test outputs once, assert they don't change. No boilerplate.

- :material-swap-horizontal: **Flexible Recorders**

    Strict JSON by default, built-in YAML, and plugins for specialised data.

- :material-cloud-upload: **Remote Backends**

    Store snapshots locally, on S3 or anywhere fsspec reaches, or in your own
    backend for a database such as Redis.

- :material-console: **CLI Tools**

    Manage snapshots from the command line: list, update, prune, lint, and more.

- :material-lock-check: **Checked in CI**

    A committed lock file records every snapshot, so CI fails on missing or
    stale ones.

</div>

## Quick Example

```bash
pip install pytest-ditto
```

```python
def summarise(prices):
    return {"count": len(prices), "total": sum(prices)}


def test_summarise(snapshot):
    result = summarise([3, 4.5])
    assert result == snapshot(result, key="summary")
```

The first run stores the result as a snapshot. Every later run compares the
result with it, and fails if it has changed.

## Where to start

- **New to pytest-ditto?** Follow [Getting Started](getting-started.md), from
  a first snapshot to checking it in CI.
- **Want to understand it?** Read [How Snapshots Work](concepts/snapshots.md)
  and [The Lock File](concepts/lock-file.md).
- **Have a task in mind?** See the guides: [recorders](guides/recorders.md),
  [remote storage](guides/backends.md), [CI](guides/ci.md) and
  [maintaining snapshots](guides/maintaining.md).
- **Upgrading from 1.x?** Read [Upgrading to 2.0](upgrading.md) first.
- **Looking something up?** See the [configuration](reference/configuration.md),
  [CLI](cli/index.md) and [API](reference/index.md) references.

[Get Started](getting-started.md){ .md-button .md-button--primary }
[CLI Reference](cli/index.md){ .md-button }
