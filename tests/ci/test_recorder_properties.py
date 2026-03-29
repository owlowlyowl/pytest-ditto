"""Property-based round-trip tests for built-in recorder implementations."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ditto import recorders

# ── Strategies ────────────────────────────────────────────────────────────────

# Primitives supported by JSON, YAML SafeDumper, and pickle.
_primitives = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)

# Recursive values compatible with both the JSON and YAML recorders.
# JSON and YAML SafeDumper/SafeLoader share the same supported type set:
# the primitives above plus lists and string-keyed dicts.
_text_serialisable_values = st.recursive(
    _primitives,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(), children, max_size=5),
    ),
    max_leaves=20,
)

# Pickle can handle everything above plus raw bytes — the key type bytes cannot
# represent. Including st.binary() here ensures type-preservation is tested too.
_pickle_values = st.recursive(
    st.one_of(_primitives, st.binary()),
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(), children, max_size=5),
    ),
    max_leaves=20,
)

_json_recorder = recorders.get("json")
_yaml_recorder = recorders.get("yaml")
_pickle_recorder = recorders.get("pickle")

# tmp_path is reused across examples — safe because each example overwrites the
# same filepath and examples are independent. Suppress Hypothesis' health check.
_no_fixture_reset = settings(suppress_health_check=[HealthCheck.function_scoped_fixture])

# ── JSON ──────────────────────────────────────────────────────────────────────


@_no_fixture_reset
@given(_text_serialisable_values)
def test_json_recorder_roundtrip_preserves_value(tmp_path, data) -> None:
    """The JSON recorder round-trips any JSON-compatible value through save and load without loss."""
    filepath = tmp_path / "snapshot.json"

    _json_recorder.save(data, filepath)
    actual = _json_recorder.load(filepath)

    assert actual == data


# ── YAML ──────────────────────────────────────────────────────────────────────


@_no_fixture_reset
@given(_text_serialisable_values)
def test_yaml_recorder_roundtrip_preserves_value(tmp_path, data) -> None:
    """The YAML recorder round-trips any YAML-compatible value through save and load without loss."""
    filepath = tmp_path / "snapshot.yaml"

    _yaml_recorder.save(data, filepath)
    actual = _yaml_recorder.load(filepath)

    assert actual == data


# ── Pickle ────────────────────────────────────────────────────────────────────


@_no_fixture_reset
@given(_pickle_values)
def test_pickle_recorder_roundtrip_preserves_value(tmp_path, data) -> None:
    """The pickle recorder round-trips any picklable value without loss, including raw bytes."""
    filepath = tmp_path / "snapshot.pkl"

    _pickle_recorder.save(data, filepath)
    actual = _pickle_recorder.load(filepath)

    assert actual == data
    assert type(actual) is type(data)
