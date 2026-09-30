import io
import json as _json
from collections.abc import Hashable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ditto.recorders import Recorder


__all__ = ("parquet", "json", "csv")


type Frame = pd.DataFrame | pd.Series

_MARKER_KEY = b"ditto"
_SERIES_COLUMN = "values"
_JSON_SEPARATORS = (",", ":")
_CSV_MARKER_PREFIX = "# ditto: "
_NAME_ATOMS = (str, int, float, bool)
_FREQ_INDEXES = (pd.DatetimeIndex, pd.TimedeltaIndex)


def _series_column(index_name: object) -> str:
    column = _SERIES_COLUMN
    n = 1
    while column == index_name:
        column = f"{_SERIES_COLUMN}_{n}"
        n += 1
    return column


def _encode_name(name: object) -> object:
    if name is None or isinstance(name, _NAME_ATOMS):
        return name
    if isinstance(name, tuple) and all(
        item is None or isinstance(item, _NAME_ATOMS) for item in name
    ):
        return list(name)
    raise TypeError(
        f"can't record a Series named {name!r}: its name must be None, "
        "a str, int, float or bool, or a tuple of those"
    )


def _decode_name(name: object) -> Hashable:
    if isinstance(name, list):
        return tuple(name)
    if name is None or isinstance(name, _NAME_ATOMS):
        return name
    raise ValueError(f"the ditto marker has an invalid Series name: {name!r}")


def _split(
    data: Frame, *, keep_freq: bool
) -> tuple[pd.DataFrame, dict[str, object] | None]:
    """The frame to write, and the marker to write with it.

    The marker is None for a DataFrame with nothing to add, so its bytes are the
    same as pandas writes. keep_freq records a DatetimeIndex or TimedeltaIndex
    freq, which no format stores itself (#178); CSV leaves it out, since it
    doesn't read a datetime index back as one.
    """
    marker: dict[str, object] = {"version": 1}
    if isinstance(data, pd.DataFrame):
        frame = data
        marker["kind"] = "frame"
    else:
        column = _series_column(data.index.name)
        frame = data.to_frame(column)
        marker |= {"kind": "series", "name": _encode_name(data.name), "column": column}
    index = data.index
    if keep_freq and isinstance(index, _FREQ_INDEXES) and index.freq is not None:
        marker["index_freq"] = index.freqstr
    return frame, None if marker == {"version": 1, "kind": "frame"} else marker


def _join(frame: pd.DataFrame, marker: dict[str, object] | None) -> Frame:
    if marker is None:
        return frame
    freq = marker.get("index_freq")
    if freq is not None:
        index = frame.index
        if not isinstance(freq, str) or not isinstance(index, _FREQ_INDEXES):
            raise ValueError(
                f"the snapshot records index freq {freq!r}, but its index loaded "
                f"as a {type(index).__name__}"
            )
        # Rebuilding the index with freq= checks the freq against the values, so
        # a snapshot whose dates don't match its freq raises rather than loading.
        frame.index = type(index)(index, freq=freq, name=index.name)
    if marker.get("kind") != "series":
        return frame
    values = frame[marker["column"]]
    assert isinstance(values, pd.Series)
    return values.rename(_decode_name(marker["name"]))


def _marker_json(marker: dict[str, object]) -> str:
    return _json.dumps(marker, separators=_JSON_SEPARATORS)


def _parquet_dumps(data: Frame) -> bytes:
    frame, marker = _split(data, keep_freq=True)
    table = pa.Table.from_pandas(frame)
    if marker is not None:
        meta = dict(table.schema.metadata or {})
        meta[_MARKER_KEY] = _marker_json(marker).encode("utf-8")
        table = table.replace_schema_metadata(meta)
    buffer = io.BytesIO()
    pq.write_table(table, buffer)
    return buffer.getvalue()


def _parquet_loads(raw: bytes) -> Frame:
    table = pq.read_table(io.BytesIO(raw))
    meta = table.schema.metadata or {}
    marker = _json.loads(meta[_MARKER_KEY]) if _MARKER_KEY in meta else None
    return _join(table.to_pandas(), marker)


parquet: Recorder[pd.DataFrame | pd.Series] = Recorder(
    dumps=_parquet_dumps, loads=_parquet_loads
)


def _json_dumps(data: Frame) -> bytes:
    frame, marker = _split(data, keep_freq=True)
    buffer = io.StringIO()
    frame.to_json(buffer, orient="table")
    text = buffer.getvalue()
    if marker is None:
        return text.encode("utf-8")
    payload = _json.loads(text)
    payload["ditto"] = marker
    # Compact separators: json.dumps(json.loads(text), separators=(",", ":"))
    # matches pandas to_json(orient="table"), so dumps(loads(raw)) == raw.
    return _json.dumps(payload, separators=_JSON_SEPARATORS).encode("utf-8")


def _json_loads(raw: bytes) -> Frame:
    payload = _json.loads(raw.decode("utf-8"))
    marker = payload.pop("ditto", None)
    text = _json.dumps(payload, separators=_JSON_SEPARATORS)
    frame = pd.read_json(io.StringIO(text), orient="table")
    return _join(frame, marker)


json: Recorder[pd.DataFrame | pd.Series] = Recorder(
    dumps=_json_dumps, loads=_json_loads
)


def _csv_dumps(data: Frame) -> bytes:
    # "\n" rather than the platform's line separator, so the bytes are the same
    # on every platform.
    frame, marker = _split(data, keep_freq=False)
    body = frame.to_csv(lineterminator="\n")
    if marker is None:
        return body.encode("utf-8")
    return f"{_CSV_MARKER_PREFIX}{_marker_json(marker)}\n{body}".encode("utf-8")


def _csv_loads(raw: bytes) -> Frame:
    # to_csv writes the index as the first column; read it back as the index,
    # not as an "Unnamed: 0" data column (#40).
    marker = None
    prefix = _CSV_MARKER_PREFIX.encode("utf-8")
    if raw.startswith(prefix):
        line, _, raw = raw.partition(b"\n")
        marker = _json.loads(line.removeprefix(prefix).decode("utf-8"))
    return _join(pd.read_csv(io.BytesIO(raw), index_col=0), marker)


csv: Recorder[pd.DataFrame | pd.Series] = Recorder(dumps=_csv_dumps, loads=_csv_loads)
