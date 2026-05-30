# ditto recorders

Lists all registered recorder plugins, showing their name, file extension,
and the source package they come from.

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
| Name | Registry key (e.g., `pickle`, `pandas_parquet`) |
| Extension | File extension (e.g., `.pkl`, `.pandas.parquet`) |
| Package | Source package (e.g., `pytest-ditto`, `pytest-ditto-pandas`) |
