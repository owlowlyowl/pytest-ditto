import io
import json as _json
from collections.abc import Hashable, Iterable
from typing import NotRequired, TypedDict, cast

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pandas.tseries.frequencies import to_offset

from ditto.recorders import Recorder


__all__ = ("parquet", "json", "csv")


type Frame = pd.DataFrame | pd.Series
type _Name = str | int | float | bool | None


class _SeriesMarker(TypedDict):
    name: _Name | list[_Name]


class _Marker(TypedDict):
    """What pandas doesn't store itself, written as JSON beside the data."""

    version: int
    series: NotRequired[_SeriesMarker]
    index_freq: NotRequired[str]


_MARKER_KEY = "ditto"
_MARKER_VERSION = 1
_SERIES_COLUMN = "values"
_CSV_MARKER_PREFIX = "# ditto: "
_NAME_ATOMS = (str, int, float, bool)
_FREQ_INDEXES = (pd.DatetimeIndex, pd.TimedeltaIndex)


def _series_column(index_names: Iterable[Hashable]) -> str:
    """A column name that no index level uses, so the frame can be written."""
    taken = set(index_names)
    column = _SERIES_COLUMN
    n = 1
    while column in taken:
        column = f"{_SERIES_COLUMN}_{n}"
        n += 1
    return column


def _name_atom(item: object) -> _Name:
    # df.iloc[i] and df.loc[label] name a Series with a numpy scalar label.
    item = item.item() if isinstance(item, np.generic) else item
    if item is None or isinstance(item, _NAME_ATOMS):
        return item
    raise TypeError(
        f"can't record a Series named {item!r}: its name must be None, a str, "
        "int, float or bool, or a tuple of those; rename() it first"
    )


def _encode_name(name: Hashable) -> _Name | list[_Name]:
    if isinstance(name, tuple):
        return [_name_atom(item) for item in name]
    return _name_atom(name)


def _decode_name(name: _Name | list[_Name]) -> Hashable:
    return tuple(name) if isinstance(name, list) else name


def _freqstr(index: pd.Index) -> str | None:
    """The index freq as a string that rebuilds it, or None if there isn't one.

    Some offsets' strings drop parameters (a CustomBusinessDay's weekmask) or
    can't be parsed back at all (a DateOffset(days=2)). Those aren't recorded:
    the index loads back without a freq, as pandas itself would load it.
    """
    if not isinstance(index, _FREQ_INDEXES) or index.freq is None:
        return None
    try:
        rebuilt = to_offset(index.freqstr)
    except ValueError:
        return None
    return index.freqstr if rebuilt == index.freq else None


def _split(data: Frame, *, keep_freq: bool) -> tuple[pd.DataFrame, str | None]:
    """The frame to write, and the marker JSON to write with it.

    The marker is None for a DataFrame with nothing to add, so its bytes are the
    same as pandas writes. keep_freq records the index freq, which no format
    stores itself (#178); CSV leaves it out, since it doesn't read a datetime
    index back as one.
    """
    marker: _Marker = {"version": _MARKER_VERSION}
    if isinstance(data, pd.Series):
        frame = data.to_frame(_series_column(data.index.names))
        marker["series"] = {"name": _encode_name(data.name)}
    else:
        frame = data
    if keep_freq and (freq := _freqstr(data.index)) is not None:
        marker["index_freq"] = freq
    if marker.keys() == {"version"}:
        return frame, None
    return frame, _json.dumps(marker, separators=(",", ":"))


def _join(frame: pd.DataFrame, marker: _Marker | None) -> Frame:
    if marker is None:
        return frame
    if marker["version"] != _MARKER_VERSION:
        raise ValueError(
            f"the ditto marker has version {marker['version']!r}; this "
            f"pytest-ditto-pandas reads version {_MARKER_VERSION}"
        )
    if (freq := marker.get("index_freq")) is not None:
        index = frame.index
        if not isinstance(index, _FREQ_INDEXES):
            raise ValueError(
                f"the snapshot records index freq {freq!r}, but its index loaded "
                f"as a {type(index).__name__}"
            )
        # Rebuilding the index with freq= checks the freq against the values, so
        # a snapshot whose dates don't match its freq raises rather than loading.
        frame.index = type(index)(index, freq=freq, name=index.name)
    if (series := marker.get("series")) is None:
        return frame
    return frame.iloc[:, 0].rename(_decode_name(series["name"]))


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
    meta = (table.schema.metadata or {}) | {_MARKER_KEY.encode(): marker.encode()}
    buffer = io.BytesIO()
    pq.write_table(table.replace_schema_metadata(meta), buffer)
    return buffer.getvalue()


def _parquet_loads(raw: bytes) -> Frame:
    meta = pq.read_schema(io.BytesIO(raw)).metadata or {}
    marker = meta.get(_MARKER_KEY.encode())
    frame = pd.read_parquet(io.BytesIO(raw))
    return _join(frame, None if marker is None else _json.loads(marker))


parquet: Recorder[Frame] = Recorder(dumps=_parquet_dumps, loads=_parquet_loads)


def _json_dumps(data: Frame) -> bytes:
    frame, marker = _split(data, keep_freq=True)
    buffer = io.StringIO()
    frame.to_json(buffer, orient="table")
    text = buffer.getvalue()
    if marker is not None:
        # Add the marker as a last top-level key, leaving pandas' own text as it
        # is. read_json(orient="table") ignores keys it doesn't know.
        text = f'{text.removesuffix("}")},"{_MARKER_KEY}":{marker}}}'
    return text.encode("utf-8")


def _json_loads(raw: bytes) -> Frame:
    text = raw.decode("utf-8")
    frame = pd.read_json(io.StringIO(text), orient="table")
    return _join(frame, _json.loads(text).get(_MARKER_KEY))


json: Recorder[Frame] = Recorder(dumps=_json_dumps, loads=_json_loads)


def _csv_dumps(data: Frame) -> bytes:
    if isinstance(data, pd.Series) and data.index.nlevels > 1:
        raise ValueError(
            "pandas.csv can't record a Series with a MultiIndex, since it reads "
            "back only the first index level; use pandas.parquet or pandas.json"
        )
    frame, marker = _split(data, keep_freq=False)
    # "\n" rather than the platform's line separator, so the bytes are the same
    # on every platform.
    body = frame.to_csv(lineterminator="\n")
    if marker is not None:
        body = f"{_CSV_MARKER_PREFIX}{marker}\n{body}"
    return body.encode("utf-8")


def _csv_marker(line: bytes) -> _Marker | None:
    """The marker on a CSV file's first line, or None if the line is data.

    A header can start with the marker prefix too (an index named "# ditto: x"),
    so the line is only a marker if the rest is a JSON object with a version.
    """
    prefix = _CSV_MARKER_PREFIX.encode("utf-8")
    if not line.startswith(prefix):
        return None
    try:
        marker = _json.loads(line.removeprefix(prefix))
    except ValueError:
        return None
    if not isinstance(marker, dict) or "version" not in marker:
        return None
    return cast("_Marker", marker)


def _csv_loads(raw: bytes) -> Frame:
    line, _, body = raw.partition(b"\n")
    marker = _csv_marker(line)
    # to_csv writes the index as the first column; read it back as the index,
    # not as an "Unnamed: 0" data column (#40).
    frame = pd.read_csv(io.BytesIO(raw if marker is None else body), index_col=0)
    return _join(frame, marker)


csv: Recorder[Frame] = Recorder(dumps=_csv_dumps, loads=_csv_loads)
