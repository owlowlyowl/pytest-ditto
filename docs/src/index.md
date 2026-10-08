---
title: pytest-ditto
---

<h1 class="ditto-brand" id="pytest-ditto">
  <img class="ditto-logo-light" src="assets/branding/logo-light.svg" alt="pytest-ditto" width="490" height="120">
  <img class="ditto-logo-dark" src="assets/branding/logo-dark.svg" alt="pytest-ditto" width="490" height="120">
</h1>

Snapshot regression testing for DataFrames in pytest, with minimal ceremony,
pluggable recorders, and local or remote storage backends.

Choose a recorder for pandas or Polars DataFrames or PyArrow Tables, then compare
snapshots with your library's usual assertions. Add a custom recorder for other
data types; storage backends work independently of the recorder.

<div class="grid cards" markdown>

- :material-camera: **Tabular Snapshots**

    Record DataFrames and Tables once, then check them with the comparison
    functions you already use.

- :material-swap-horizontal: **Pluggable Recorders**

    Strict JSON and YAML are built in. Plugins add Parquet, Arrow IPC, CSV and
    more; write a recorder for your own data types and formats.

- :material-cloud-upload: **Local and Remote Backends**

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
pip install "pytest-ditto[pandas]"
```

```python
import ditto
import pandas as pd


@ditto.pandas.parquet
def test_sales_totals(snapshot):
    sales = pd.DataFrame({"region": ["east", "east", "west"], "amount": [10, 5, 8]})
    totals = sales.groupby("region")["amount"].sum().to_frame()
    pd.testing.assert_frame_equal(totals, snapshot(totals, key="totals"))
```

The mark selects Parquet; `snapshot()` handles storage and returns the recorded
DataFrame. The first run records the result, and later runs compare against it.
Run `ditto verify` in CI so a missing snapshot fails instead of being recorded
again. See the [pandas](plugins/pandas.md), [Polars](plugins/polars.md) and
[PyArrow](plugins/pyarrow.md) guides for their recorders and format limitations.

## Other data types

Strict JSON works without a recorder plugin:

```bash
pip install pytest-ditto
```

<!-- test: passes -->
```python
def summarise(prices):
    return {"count": len(prices), "total": sum(prices)}


def test_summarise(snapshot):
    result = summarise([3, 4.5])
    assert result == snapshot(result, key="summary")
```

Use a [custom recorder](guides/custom-recorders.md) for other types that you can
serialise and read back for comparison, and a
[storage backend](guides/backends.md) to choose where their snapshots go.

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
