import io
import json as _json
from collections.abc import Hashable, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pandas.tseries.frequencies import to_offset

from ditto.exceptions import DittoUnsupportedDataError
from ditto.recorders import Recorder


__all__ = ("parquet", "json", "csv")


type Frame = pd.DataFrame | pd.Series

_MARKER_KEY = b"ditto"
_SERIES_COLUMN = "values"
_JSON_SEPARATORS = (",", ":")
_CSV_MARKER_PREFIX = "# ditto: "
_NAME_ATOMS = (str, int, float, bool)
_FREQ_INDEXES = (pd.DatetimeIndex, pd.TimedeltaIndex)
_MARKER_VERSION = 1


def _series_column(index_names: Iterable[Hashable]) -> str:
    """A column name that no index level uses, so the frame can be written."""
    taken = set(index_names)
    column = _SERIES_COLUMN
    n = 1
    while column in taken:
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


def _freqstr(index: pd.Index) -> str | None:
    """The index freq as a string that rebuilds it, or None if there isn't one.

    Some offsets' strings drop parameters (a CustomBusinessDay's weekmask) or
    can't be parsed back at all (a DateOffset(days=2)). Those aren't recorded:
    the index loads back without a freq, as pandas itself would load it.
    """
    if not isinstance(index, _FREQ_INDEXES) or index.freq is None:
        return None
    freqstr = index.freqstr
    try:
        rebuilt = to_offset(freqstr)
    except ValueError:
        return None
    return freqstr if rebuilt == index.freq else None


def _check_marker(marker: object) -> dict[str, object]:
    """The marker, if it is one this version of the recorders can load."""
    if not isinstance(marker, dict):
        raise ValueError(f"the ditto marker isn't a JSON object: {marker!r}")
    if marker.get("version") != _MARKER_VERSION:
        raise ValueError(
            f"the ditto marker has version {marker.get('version')!r}; this "
            f"pytest-ditto-pandas reads version {_MARKER_VERSION}"
        )
    kind = marker.get("kind")
    if kind not in ("frame", "series"):
        raise ValueError(f"the ditto marker has an unknown kind: {kind!r}")
    if kind == "series" and (
        "name" not in marker or not isinstance(marker.get("column"), str)
    ):
        raise ValueError(f"the ditto marker for a Series is incomplete: {marker!r}")
    freq = marker.get("index_freq")
    if freq is not None and not isinstance(freq, str):
        raise ValueError(f"the ditto marker has an invalid index freq: {freq!r}")
    return marker


def _split(
    data: Frame, *, keep_freq: bool
) -> tuple[pd.DataFrame, dict[str, object] | None]:
    """The frame to write, and the marker to write with it.

    The marker is None for a DataFrame with nothing to add, so its bytes are the
    same as pandas writes. keep_freq records a DatetimeIndex or TimedeltaIndex
    freq, which no format stores itself (#178); CSV leaves it out, since it
    doesn't read a datetime index back as one.
    """
    marker: dict[str, object] = {"version": _MARKER_VERSION}
    if isinstance(data, pd.DataFrame):
        frame = data
        marker["kind"] = "frame"
    else:
        column = _series_column(data.index.names)
        frame = data.to_frame(column)
        marker |= {"kind": "series", "name": _encode_name(data.name), "column": column}
    freqstr = _freqstr(data.index) if keep_freq else None
    if freqstr is not None:
        marker["index_freq"] = freqstr
    if marker == {"version": _MARKER_VERSION, "kind": "frame"}:
        return frame, None
    return frame, marker


def _join(frame: pd.DataFrame, marker: object) -> Frame:
    if marker is None:
        return frame
    marker = _check_marker(marker)
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
    values = frame[str(marker["column"])]
    assert isinstance(values, pd.Series)
    return values.rename(_decode_name(marker["name"]))


def _marker_json(marker: dict[str, object]) -> str:
    return _json.dumps(marker, separators=_JSON_SEPARATORS)


def _parquet_dumps(data: Frame) -> bytes:
    # pandas writes and reads the data, so the file keeps what pandas stores
    # (attrs, for one) on every pandas version. A marker is added to the schema
    # metadata of the file pandas wrote.
    frame, marker = _split(data, keep_freq=True)
    buffer = io.BytesIO()
    frame.to_parquet(buffer)
    if marker is None:
        return buffer.getvalue()
    table = pq.read_table(io.BytesIO(buffer.getvalue()))
    meta = dict(table.schema.metadata or {})
    meta[_MARKER_KEY] = _marker_json(marker).encode("utf-8")
    buffer = io.BytesIO()
    pq.write_table(table.replace_schema_metadata(meta), buffer)
    return buffer.getvalue()


def _parquet_loads(raw: bytes) -> Frame:
    meta = pq.read_schema(io.BytesIO(raw)).metadata or {}
    marker = _json.loads(meta[_MARKER_KEY]) if _MARKER_KEY in meta else None
    return _join(pd.read_parquet(io.BytesIO(raw)), marker)


parquet: Recorder[pd.DataFrame | pd.Series] = Recorder(
    dumps=_parquet_dumps, loads=_parquet_loads
)


def _json_dtype_problem(dtype: object, *, in_index: bool) -> str | None:
    """Why JSON can't keep values of this dtype, or None if it can."""
    if isinstance(dtype, np.dtype):
        if dtype.kind in "iu" and dtype != np.int64:
            return "JSON reads it back as int64"
        if dtype.kind == "f" and dtype != np.float64:
            return "JSON reads it back as float64"
        if dtype.kind == "M" and np.datetime_data(dtype)[0] != "ns":
            return "JSON reads it back as datetime64[ns]"
        if dtype.kind == "m":
            return "pandas can't read timedelta data back from JSON"
        if dtype.kind == "c":
            return "JSON can't store complex numbers"
    elif isinstance(dtype, pd.DatetimeTZDtype) and dtype.unit != "ns":
        return f"JSON reads it back as datetime64[ns, {dtype.tz}]"
    elif isinstance(dtype, pd.IntervalDtype):
        return "pandas can't read interval data back from JSON"
    elif isinstance(dtype, pd.PeriodDtype) and not in_index:
        return "pandas can't write a period column to JSON"
    return None


def _json_problems(data: Frame) -> list[str]:
    """What in the data JSON can't load back as it was.

    Checked by dtype and index name before writing, so the recorder raises
    rather than record a snapshot that loads back different. pandas writes
    floats to 10 decimal places, which loses precision and turns tiny values
    into zero; that depends on the values, so it isn't checked here.
    """
    problems = []
    if isinstance(data, pd.DataFrame):
        columns = [(f"column {name!r}", dtype) for name, dtype in data.dtypes.items()]
    else:
        columns = [("the Series", data.dtype)]
    for label, dtype in columns:
        if (reason := _json_dtype_problem(dtype, in_index=False)) is not None:
            problems.append(f"{label} ({dtype}): {reason}")
    index = data.index
    dtypes = list(index.dtypes) if isinstance(index, pd.MultiIndex) else [index.dtype]
    for name, dtype in zip(index.names, dtypes, strict=True):
        label = "the index" if index.nlevels == 1 else f"index level {name!r}"
        if (reason := _json_dtype_problem(dtype, in_index=True)) is not None:
            problems.append(f"{label} ({dtype}): {reason}")
        if name == "index":
            problems.append(f"{label} is named 'index': JSON reads it back unnamed")
    return problems


def _json_dumps(data: Frame) -> bytes:
    if problems := _json_problems(data):
        raise DittoUnsupportedDataError(
            "pandas.json",
            problems,
            "Use @ditto.pandas.parquet, which keeps these, or convert the data "
            'first, for example with .astype() or .as_unit("ns").',
        )
    frame, marker = _split(data, keep_freq=True)
    buffer = io.StringIO()
    # date_unit="ns" rather than the default, milliseconds, which truncates
    # finer datetimes.
    frame.to_json(buffer, orient="table", date_unit="ns")
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


def _csv_marker(line: bytes) -> object:
    """The marker on a CSV file's first line, or None if the line is data.

    A header can start with the marker prefix too (an index named "# ditto: x"),
    so the line is only a marker if the rest is a JSON object with a version.
    """
    prefix = _CSV_MARKER_PREFIX.encode("utf-8")
    if not line.startswith(prefix):
        return None
    try:
        marker = _json.loads(line.removeprefix(prefix).decode("utf-8"))
    except ValueError:
        return None
    return marker if isinstance(marker, dict) and "version" in marker else None


def _csv_loads(raw: bytes) -> Frame:
    # to_csv writes the index as the first column; read it back as the index,
    # not as an "Unnamed: 0" data column (#40).
    line, _, body = raw.partition(b"\n")
    marker = _csv_marker(line)
    if marker is not None:
        raw = body
    return _join(pd.read_csv(io.BytesIO(raw), index_col=0), marker)


csv: Recorder[pd.DataFrame | pd.Series] = Recorder(dumps=_csv_dumps, loads=_csv_loads)
