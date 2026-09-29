# The Snapshot Fixture

The `snapshot` fixture is the core of pytest-ditto. It records and replays
test outputs for regression testing.

## Basic Usage

```python
def test_fn(snapshot) -> None:
    result = compute_something()
    assert result == snapshot(result, key="something")
```

The `snapshot` callable takes two arguments:

- **`data`** — the value to snapshot (any serialisable object)
- **`key`** — a unique identifier within this test

## How It Works

```mermaid
graph LR
    A[First Run] --> B{Snapshot exists?}
    B -->|No| C[Save data, return data]
    B -->|Yes| D[Load stored data, return it]
    C --> E[Test passes]
    D --> F[assert result == stored]
```

1. **First run (recording):** No stored snapshot exists. The fixture saves `data`
   to the configured backend and returns it. Since `assert data == data`, the
   test passes.

2. **Subsequent runs (replay):** The stored snapshot is loaded and returned.
   The test asserts that the current result matches the stored value.

## Multiple Snapshots Per Test

Use distinct keys for each snapshot within a test:

```python
def test_pipeline(snapshot):
    raw = fetch_data()
    processed = transform(raw)
    
    assert raw == snapshot(raw, key="raw_input")
    assert processed == snapshot(processed, key="transformed")
```

## Duplicate Key Detection

Using the same key twice in a single test raises
`DuplicateSnapshotKeyError`:

```python
def test_bad(snapshot):
    snapshot(1, key="x")
    snapshot(2, key="x")  # raises DuplicateSnapshotKeyError
```

## Snapshot Keys

A key is a string naming one snapshot within a test. It can't contain `@`, `/`,
`\` or control characters; `snapshot()` raises `ValueError` for such a key.
The `@` separates the test's name from the key in a snapshot's name, and a
test's name can itself contain `@` through a parametrize ID, so keeping it out
of keys keeps every snapshot name unambiguous.

## Snapshot Storage Location

By default, snapshots are stored in a `.ditto/` directory adjacent to the
test file. The filename format is:

```
.ditto/<module>.<group>@<key>.<identifier>
```

For example, a test in `tests/test_api.py`:

```python
@ditto.json
def test_response(snapshot):
    data = get_response()
    assert data == snapshot(data, key="body")
```

Stores to: `.ditto/test_api.test_response@body.json`

The test name includes any parametrize ID, which can hold characters a file
name can't. In `file://` snapshot names, `%`, `/` and the characters Windows
forbids in file names (`\ : * ? " < > |` and control characters) are
percent-encoded, so the files work on every platform:

| Test | File |
|---|---|
| `test_at[12:00]` | `.ditto/test_api.test_at[12%3A00]@body.json` |
| `test_path[data/in.csv]` | `.ditto/test_api.test_path[data%2Fin.csv]@body.json` |
| `test_pct[50%]` | `.ditto/test_api.test_pct[50%25]@body.json` |

Other characters are left as they are, so most names aren't changed. Remote
backends, which don't store snapshots as local files, use names without
encoding.

## Updating Snapshots

When your code intentionally changes behaviour, regenerate snapshots:

```bash
pytest --ditto-update
# or
ditto update
```

## Pruning Stale Snapshots

Remove snapshots that are no longer used by any test:

```bash
pytest --ditto-prune
# or
ditto prune
```

!!! warning
    Using `-k` for a partial test run may falsely classify snapshots for
    un-run tests as unused.
