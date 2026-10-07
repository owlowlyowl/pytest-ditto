# Getting Started

This tutorial takes one snapshot test from first run to CI: record a
snapshot, see it catch a change, accept the change, and check everything in CI.

## Install

```bash
pip install pytest-ditto
```

pytest-ditto is a pytest plugin, so installing it is all the setup pytest
needs. It also installs the `ditto` command, which manages snapshots.

## Write a snapshot test

Create `tests/test_prices.py`:

<!-- test: passes -->
```python
def summarise(prices):
    return {"count": len(prices), "total": sum(prices)}


def test_summarise(snapshot):
    result = summarise([3, 4.5])
    assert result == snapshot(result, key="summary")
```

The test asks for the `snapshot` fixture and calls it with the value to keep
and a key that names it. `snapshot()` returns the stored value, and the test
compares its result with it.

## Record the snapshot

Run the test:

```bash
pytest
```

The snapshot doesn't exist yet, so this run stores it and the test passes.
After the test results, ditto prints a report of what it did:

```text { .text-diagram }
╭──────────────── ditto snapshot report ────────────────╮
│ 1 created                                             │
│                                                       │
│ tests/test_prices.py                                  │
│   test_summarise                                      │
│     created      summary  json                        │
│                                                       │
│   lock         ditto.lock written  1 added, 0 removed │
╰───────────────────────────────────────────────────────╯
```

Two files have appeared. The snapshot, stored as JSON in a `.ditto` directory
next to the test file:

```
tests/.ditto/tests.test_prices.test_summarise@summary~be6a9abada17b59e.json
```

```json
{
  "count": 2,
  "total": 7.5
}
```

And `ditto.lock`, in your project root, which records every snapshot your
suite owns. You'll commit both. [Snapshot Names](concepts/naming.md) explains
the file name, and [The Lock File](concepts/lock-file.md) explains the lock.

Run `pytest` again and the test compares its result with the stored snapshot.
It still passes.

## Catch a change

Now change the code so it rounds the total:

```python
def summarise(prices):
    return {"count": len(prices), "total": round(sum(prices))}
```

Run `pytest`, and the test fails, showing how the result differs from the
snapshot:

```
E       AssertionError: assert {'count': 2, 'total': 8} == {'count': 2, 'total': 7.5}
E         Differing items:
E         {'total': 8} != {'total': 7.5}
```

## Accept the change

If the change is a bug, fix the code. If it's what you meant, re-record the
snapshot from the current output:

```bash
ditto update
```

```text { .text-diagram }
╭──── ditto snapshot report ─────╮
│ 1 rewritten                    │
│                                │
│ tests/test_prices.py           │
│   test_summarise               │
│     rewritten    summary  json │
╰────────────────────────────────╯
```

`ditto update` accepts whatever the code produces now, so review the snapshot
diff before you commit it:

```diff
 {
   "count": 2,
-  "total": 7.5
+  "total": 8
 }
```

## Commit

Commit the snapshot directory and `ditto.lock` with your code:

```bash
git add tests/.ditto ditto.lock tests/test_prices.py
```

## Check in CI

In CI, run `ditto verify` rather than `pytest`:

```bash
ditto verify
```

```
ditto verify: no drift in 1 target: tests/.ditto
```

It runs your tests without writing anything, and also fails if a snapshot the
lock records is missing. A plain `pytest` run would instead record a missing
snapshot from the current output and pass. See [Running in CI](guides/ci.md).

## Next steps

- [How Snapshots Work](concepts/snapshots.md): what `snapshot()` returns in
  each mode, keys, and marks.
- [Recorders](guides/recorders.md): store YAML, pandas, polars or PyArrow data
  instead of JSON.
- [Maintaining Snapshots](guides/maintaining.md): update, rename and clean up
  snapshots as your tests change.
- [Storage Backends](guides/backends.md): keep snapshots on S3, in a database or
  anywhere fsspec reaches.
