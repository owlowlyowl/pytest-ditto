"""The pandas recorders, as registered through the 2.0 plugin contract."""

import io
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

import ditto
from ditto import recorders

NAMES = ["pandas.parquet", "pandas.json", "pandas.csv"]


def _sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})


@pytest.mark.parametrize("name", NAMES)
def test_registers_each_recorder_under_its_dotted_name(name: str) -> None:
    """Each recorder is discoverable by its `pandas.<format>` name."""
    assert name in recorders.RECORDER_REGISTRY


def test_registrations_keep_the_plugin_contract() -> None:
    """No contract problem involves a pandas recorder."""
    affected = {n for p in recorders.RECORDER_REGISTRY.problems for n in p.names}

    assert affected.isdisjoint(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_derives_a_namespaced_mark_for_each_recorder(name: str) -> None:
    """`ditto.pandas.<format>` is the mark for `record("pandas.<format>")`."""
    fmt = name.removeprefix("pandas.")

    actual = getattr(ditto.pandas, fmt)

    expected = pytest.mark.record(name)
    assert actual == expected


@ditto.pandas.parquet
def test_parquet_mark_selects_the_parquet_recorder(snapshot) -> None:
    """The parquet mark gives the snapshot fixture the parquet recorder, named
    `pandas.parquet` in snapshot filenames."""
    actual = snapshot.recorder

    assert actual is recorders.get("pandas.parquet")
    assert snapshot.recorder_name == "pandas.parquet"


@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
def test_round_trips_a_dataframe(name: str) -> None:
    """Parquet and JSON load back exactly the DataFrame they saved."""
    df = _sample_dataframe()
    recorder = recorders.get(name)
    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


@pytest.mark.parametrize(
    "df",
    [
        pd.DataFrame(np.arange(6.0).reshape(3, 2)),
        pd.DataFrame({"a": [1.0], 0: [2.0], 1.5: [3.0], True: [4.0]}),
    ],
    ids=["integer", "mixed"],
)
def test_json_round_trips_a_dataframe_with_non_string_column_names(
    df: pd.DataFrame,
) -> None:
    """JSON loads columns named by an int, float or bool back with their values."""
    recorder = recorders.get("pandas.json")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


def test_json_round_trips_a_dataframe_with_a_non_string_index_name() -> None:
    """JSON loads an index named by an int back with its name and values."""
    df = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.Index([5, 6], name=0))
    recorder = recorders.get("pandas.json")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


def test_csv_round_trips_a_dataframe_except_for_the_index_type() -> None:
    """CSV loads back the saved values, with the RangeIndex read back as Int64.

    check_index_type=False because CSV has no type metadata: a RangeIndex is written
    as plain integers and read back as an Int64 index. Only single-level numeric or
    string indices round-trip reliably — DatetimeIndex, PeriodIndex, CategoricalIndex,
    and MultiIndex are not supported.
    """
    df = _sample_dataframe()
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df, check_index_type=False)


def test_csv_ends_lines_with_newlines_on_every_platform() -> None:
    """CSV bytes don't depend on the platform's line separator."""
    actual = recorders.get("pandas.csv").dumps(_sample_dataframe())

    assert b"\n" in actual
    assert b"\r" not in actual


def test_csv_reads_the_index_back_as_the_index() -> None:
    """The saved index is restored as the index, not as a data column (#40)."""
    df = _sample_dataframe()
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    assert list(actual.columns) == ["a", "b"]


def test_csv_round_trips_a_string_index_exactly() -> None:
    """A named string index survives a CSV round trip unchanged."""
    df = _sample_dataframe().set_index(pd.Index(["x", "y", "z"], name="key"))
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


def _sample_series(
    name: object = "x",
    index: pd.Index | None = None,
) -> pd.Series:
    if index is None:
        index = pd.Index(["a", "b"], name="k")
    return pd.Series([1.0, 2.0], name=name, index=index)


SERIES_CASES = [
    pytest.param(_sample_series(name="x"), id="named"),
    pytest.param(_sample_series(name=None), id="unnamed"),
    pytest.param(_sample_series(name=0), id="int-zero"),
    pytest.param(_sample_series(name="0"), id="str-zero"),
    pytest.param(_sample_series(name=True), id="bool-true"),
    pytest.param(_sample_series(name=1), id="int-one"),
    pytest.param(_sample_series(name="k"), id="name-equals-index-name"),
    pytest.param(_sample_series(name=("x",)), id="1-tuple"),
    pytest.param(_sample_series(name=("x", "y")), id="2-tuple"),
    pytest.param(_sample_series(name=("x", None)), id="tuple-with-none"),
    # df.iloc[i] and df.loc[label] name a Series with a numpy scalar label.
    pytest.param(_sample_series(name=np.int64(10)), id="numpy-int"),
    pytest.param(_sample_series(name=np.bool_(True)), id="numpy-bool"),
    pytest.param(_sample_series(name=("x", np.int64(2))), id="tuple-with-numpy-int"),
    pytest.param(
        _sample_series(index=pd.Index(["a", "b"], name="values")),
        id="index-named-values",
    ),
    pytest.param(
        _sample_series(index=pd.Index(["a", "b"], name="values_1")),
        id="index-named-values-1",
    ),
]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("series", SERIES_CASES)
def test_round_trips_a_series(name: str, series: pd.Series) -> None:
    """Each recorder loads back the Series it saved, including its name."""
    recorder = recorders.get(name)

    actual = recorder.loads(recorder.dumps(series))

    pd.testing.assert_series_equal(actual, series)


@pytest.mark.parametrize("name", NAMES)
def test_one_column_dataframe_still_loads_as_a_dataframe(name: str) -> None:
    """A one-column DataFrame is not mistaken for a Series."""
    df = pd.DataFrame({"values": [1.0, 2.0]}, index=pd.Index(["a", "b"], name="k"))
    recorder = recorders.get(name)

    actual = recorder.loads(recorder.dumps(df))

    assert isinstance(actual, pd.DataFrame)
    pd.testing.assert_frame_equal(actual, df)


@pytest.mark.parametrize("attrs", [{}, {"units": "kg"}], ids=["plain", "with-attrs"])
def test_parquet_dataframe_bytes_match_to_parquet(attrs: dict[str, str]) -> None:
    """A DataFrame's parquet bytes, attrs included, are DataFrame.to_parquet's."""
    df = _sample_dataframe()
    df.attrs = attrs
    buffer = io.BytesIO()
    df.to_parquet(buffer)

    assert recorders.get("pandas.parquet").dumps(df) == buffer.getvalue()


def test_json_dataframe_bytes_match_to_json() -> None:
    """A DataFrame's JSON bytes are unchanged from to_json(orient='table')."""
    df = _sample_dataframe()
    buffer = io.StringIO()
    df.to_json(buffer, orient="table")

    assert recorders.get("pandas.json").dumps(df) == buffer.getvalue().encode("utf-8")


def test_csv_dataframe_bytes_match_to_csv() -> None:
    """A DataFrame's CSV bytes are unchanged from to_csv(lineterminator='\\n')."""
    df = _sample_dataframe()

    expected = df.to_csv(lineterminator="\n").encode("utf-8")
    assert recorders.get("pandas.csv").dumps(df) == expected


MARKED_DATA = [
    pytest.param(_sample_series(), id="series"),
    pytest.param(
        pd.DataFrame({"a": [1.0, 2.0]}, index=pd.date_range("2020-01-01", periods=2)),
        id="frame-with-freq",
    ),
]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("data", MARKED_DATA)
def test_rewriting_a_series_or_freq_snapshot_reproduces_its_bytes(
    name: str, data: pd.DataFrame | pd.Series
) -> None:
    """Loading a Series or freq snapshot and dumping it again gives the same bytes."""
    recorder = recorders.get(name)
    raw = recorder.dumps(data)

    actual = recorder.dumps(recorder.loads(raw))

    assert actual == raw


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize(
    "series_name",
    [
        pytest.param(pd.Timestamp("2020-01-01"), id="timestamp"),
        pytest.param(frozenset({1}), id="frozenset"),
        pytest.param(("a", ("b", 2)), id="nested-tuple"),
    ],
)
def test_unsupported_series_name_raises_typeerror(
    name: str, series_name: object
) -> None:
    """A Series whose name is not JSON-safe is rejected at write time."""
    series = _sample_series(name=series_name)
    recorder = recorders.get(name)

    with pytest.raises(TypeError, match=r"rename\(\) it"):
        recorder.dumps(series)


def test_csv_rejects_a_series_with_a_multiindex() -> None:
    """CSV reads back only one index level, so it refuses to record more."""
    index = pd.MultiIndex.from_tuples([("a", 1), ("b", 2)], names=["k", "n"])
    series = pd.Series([1.0, 2.0], name="x", index=index)

    with pytest.raises(ValueError, match="MultiIndex"):
        recorders.get("pandas.csv").dumps(series)


def _index_type_kept(name: str) -> bool:
    """Whether a recorder keeps a DatetimeIndex's unit.

    JSON reads datetimes back as nanoseconds, so on pandas 3 a microsecond index
    changes dtype; see the format notes in docs/src/plugins/pandas.md.
    """
    return name != "pandas.json"


FREQ_INDEXES = [
    pytest.param(pd.date_range("2020-01-01", periods=3, name="d"), id="daily"),
    pytest.param(pd.date_range("2020-01-31", periods=3, freq="ME"), id="month-end"),
    pytest.param(
        pd.date_range("2020-01-01", periods=3, freq="2h", tz="Australia/Sydney"),
        id="tz-aware",
    ),
    pytest.param(pd.bdate_range("2020-01-03", periods=3), id="business-day"),
]


@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
@pytest.mark.parametrize("index", FREQ_INDEXES)
def test_round_trips_a_dataframe_index_freq(name: str, index: pd.DatetimeIndex) -> None:
    """Parquet and JSON restore a DatetimeIndex's freq, which pandas drops (#178)."""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=index)
    recorder = recorders.get(name)

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df, check_index_type=_index_type_kept(name))
    assert actual.index.freq == df.index.freq


@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
@pytest.mark.parametrize("index", FREQ_INDEXES)
def test_round_trips_a_series_index_freq(name: str, index: pd.DatetimeIndex) -> None:
    """A Series on a DatetimeIndex keeps both its name and the index freq."""
    series = pd.Series([1.0, 2.0, 3.0], name="x", index=index)
    recorder = recorders.get(name)

    actual = recorder.loads(recorder.dumps(series))

    pd.testing.assert_series_equal(
        actual, series, check_index_type=_index_type_kept(name)
    )
    assert actual.index.freq == series.index.freq


def test_parquet_round_trips_a_timedelta_index_freq() -> None:
    """Parquet restores a TimedeltaIndex's freq too."""
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=pd.timedelta_range("1D", periods=3))
    recorder = recorders.get("pandas.parquet")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
def test_datetime_index_without_a_freq_stays_without_one(name: str) -> None:
    """An index with no freq isn't given one on load, and writes no marker."""
    index = pd.DatetimeIndex(["2020-01-01", "2020-01-02", "2020-01-05"])
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=index)
    recorder = recorders.get(name)
    raw = recorder.dumps(df)

    actual = recorder.loads(raw)

    pd.testing.assert_frame_equal(actual, df, check_index_type=_index_type_kept(name))
    assert actual.index.freq is None
    assert b"ditto" not in raw


def test_json_rejects_a_freq_that_does_not_match_the_dates() -> None:
    """A snapshot whose stored freq doesn't fit its dates fails to load."""
    df = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.date_range("2020-01-01", periods=2))
    recorder = recorders.get("pandas.json")
    raw = recorder.dumps(df).replace(b'"index_freq":"D"', b'"index_freq":"h"')

    with pytest.raises(ValueError):
        recorder.loads(raw)


def test_csv_does_not_record_an_index_freq() -> None:
    """CSV reads dates back as strings, so it doesn't store a freq to restore."""
    df = pd.DataFrame({"a": [1.0, 2.0]}, index=pd.date_range("2020-01-01", periods=2))

    actual = recorders.get("pandas.csv").dumps(df)

    assert actual == df.to_csv(lineterminator="\n").encode("utf-8")


@pytest.mark.parametrize(
    "offset",
    [
        pytest.param(
            pd.offsets.CustomBusinessDay(weekmask="Mon Tue Wed Thu"),
            id="custom-business-day",
        ),
        pytest.param(pd.DateOffset(days=2), id="date-offset"),
    ],
)
@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
def test_freq_its_string_cannot_rebuild_is_not_recorded(
    name: str, offset: pd.DateOffset
) -> None:
    """A freq whose string loses parameters or can't be parsed loads back as None.

    Restoring "C" would give a CustomBusinessDay with the default weekmask, and
    "<DateOffset: days=2>" doesn't parse, so neither is stored.
    """
    index = pd.date_range("2020-01-06", periods=4, freq=offset)
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0]}, index=index)
    recorder = recorders.get(name)

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(
        actual, df, check_freq=False, check_index_type=_index_type_kept(name)
    )
    assert actual.index.freq is None


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(_sample_dataframe(), id="frame"),
        pytest.param(
            pd.DataFrame({"a": [1.0]}, index=pd.date_range("2020-01-01", periods=1)),
            id="frame-with-marker",
        ),
    ],
)
def test_parquet_round_trips_attrs(data: pd.DataFrame) -> None:
    """DataFrame attrs survive the parquet recorder, with or without a marker."""
    df = data.copy()
    df.attrs = {"units": "kg"}
    recorder = recorders.get("pandas.parquet")

    actual = recorder.loads(recorder.dumps(df))

    assert actual.attrs == {"units": "kg"}


def test_parquet_loads_attrs_from_a_file_pandas_wrote() -> None:
    """An existing snapshot written by DataFrame.to_parquet keeps its attrs."""
    df = _sample_dataframe()
    df.attrs = {"units": "kg"}
    buffer = io.BytesIO()
    df.to_parquet(buffer)

    actual = recorders.get("pandas.parquet").loads(buffer.getvalue())

    pd.testing.assert_frame_equal(actual, df)
    assert actual.attrs == {"units": "kg"}


@pytest.mark.parametrize("name", ["pandas.parquet", "pandas.json"])
def test_round_trips_a_series_with_a_multiindex_level_named_values(name: str) -> None:
    """The Series column avoids every index level's name, not just the first."""
    index = pd.MultiIndex.from_tuples([("a", 1), ("b", 2)], names=["values", "k"])
    series = pd.Series([1.0, 2.0], name="x", index=index)
    recorder = recorders.get(name)

    actual = recorder.loads(recorder.dumps(series))

    pd.testing.assert_series_equal(actual, series)


@pytest.mark.parametrize("index_name", ["# ditto: hello", '# ditto: {"a": 1}'])
def test_csv_header_that_starts_like_a_marker_is_read_as_data(index_name: str) -> None:
    """Only a complete marker is taken as one; other headers load as normal."""
    df = pd.DataFrame({"a": [1, 2]}, index=pd.Index(["x", "y"], name=index_name))
    recorder = recorders.get("pandas.csv")

    actual = recorder.loads(recorder.dumps(df))

    pd.testing.assert_frame_equal(actual, df)


@pytest.mark.parametrize("name", ["pandas.json", "pandas.csv"])
def test_rejects_a_marker_with_an_unknown_version(name: str) -> None:
    """A marker from a newer plugin fails to load rather than loading wrongly."""
    recorder = recorders.get(name)
    raw = recorder.dumps(_sample_series()).replace(b'"version":1', b'"version":2')

    with pytest.raises(ValueError, match="ditto marker has version 2"):
        recorder.loads(raw)


def test_parquet_rejects_a_marker_with_an_unknown_version() -> None:
    """The version check covers the marker in parquet schema metadata too."""
    raw = recorders.get("pandas.parquet").dumps(_sample_series())
    table = pq.read_table(io.BytesIO(raw))
    meta = dict(table.schema.metadata)
    meta[b"ditto"] = meta[b"ditto"].replace(b'"version":1', b'"version":2')
    buffer = io.BytesIO()
    pq.write_table(table.replace_schema_metadata(meta), buffer)

    with pytest.raises(ValueError, match="ditto marker has version 2"):
        recorders.get("pandas.parquet").loads(buffer.getvalue())


# ── Committed snapshots ───────────────────────────────────────────────────────

SNAPSHOTS = Path(__file__).parent / ".ditto"


def _recorder_name(path: Path) -> str:
    """The recorder name that ends a snapshot filename, e.g. `pandas.csv`."""
    return path.name.rpartition("@")[2].partition(".")[2]


# pandas 3 writes string columns with "extDtype":"str" and pandas 2 doesn't, so
# the committed snapshots, written by pandas 3, only re-dump byte for byte there.
@pytest.mark.skipif(
    int(pd.__version__.split(".")[0]) < 3,
    reason="the committed snapshots were written by pandas 3",
)
@pytest.mark.parametrize(
    "path",
    [
        p
        for p in sorted(SNAPSHOTS.iterdir())
        if _recorder_name(p) in {"pandas.csv", "pandas.json"}
    ],
    ids=lambda p: p.name,
)
def test_rewriting_a_committed_text_snapshot_reproduces_its_bytes(path: Path) -> None:
    """Loading a committed snapshot and dumping it again gives the same bytes."""
    recorder = recorders.get(_recorder_name(path))
    raw = path.read_bytes()

    actual = recorder.dumps(recorder.loads(raw))

    assert actual == raw
