# ditto recorders

Lists all registered recorder plugins, showing their name, the mark derived
from it, their identifier, and the source package they come from. It reads
installed package metadata only and imports no plugin. If any
registrations break the plugin contract, it says how many and points to
`ditto doctor`.

## Usage

```
ditto recorders
```

## Screenshot

![ditto recorders](../img/ditto-recorders.png)

## Output

Displays a table with columns:

| Column | Description |
|--------|-------------|
| Name | Recorder name, as used in `@ditto.record("name")` (e.g., `json`, `pandas.parquet`) |
| Mark | Mark derived from the name (e.g., `@ditto.json`, `@ditto.pandas.parquet`) |
| Identifier | Snapshot file suffix, taken from the name (e.g., `.json`, `.pandas.parquet`) |
| Package | Source package (e.g., `pytest-ditto`, `pytest-ditto-pandas`) |
