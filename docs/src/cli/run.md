# ditto run

Runs pytest and reports snapshot activity via the ditto session report. Any
extra arguments are forwarded directly to pytest.

## Usage

```
ditto run [PATH] [PYTEST_ARGS...]
```

## Examples

```bash
# Run all tests
ditto run

# Run specific directory
ditto run tests/ci/

# Run with filter
ditto run tests/ci/ -k test_foo
```

## Behaviour

- Forwards all arguments to `pytest`
- After the test run completes, displays a summary of snapshot activity:
  created, updated, pruned, and would-prune snapshots

## The session report

The report is written to stderr at the end of the session, and only when there
is something to report. Each section gives a count, then groups its snapshots
under the target they belong to:

```
╭─ ditto snapshot report ───────────────────────╮
│   created  2                                  │
│     tests/.ditto                              │
│ tests/test_a.py::test_numbers[1]  value  json │
│ tests/test_a.py::test_frame       df     json │
│   updated  1                                  │
│     tests/.ditto                              │
│ tests/test_a.py::test_numbers[1]  value  json │
╰───────────────────────────────────────────────╯
```

Each snapshot is named by the test that owns it, its key, and its recorder —
the same three facts `ditto list` shows, so a name means one thing everywhere.
Every name gets a line of its own under its target, so a long name wraps
without knocking the rest out of alignment.

A `pruned` or `would prune` snapshot is listed under its target by its storage
name, because a snapshot a prune deletes is one `ditto.lock` does not record —
the lock holds no identity for it, and the storage name is what finds the file.
