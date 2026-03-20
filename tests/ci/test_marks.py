import pytest

import ditto


# --- Default behaviour ---


def test_defaults_to_pickle_when_no_mark_is_applied(snapshot) -> None:
    """Without a record mark, the snapshot fixture uses pickle format."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".pkl"


# --- Convenience marks ---


@ditto.pickle
def test_uses_pickle_when_pickle_mark_is_applied(snapshot) -> None:
    """The @ditto.pickle convenience mark selects pickle format for the snapshot."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".pkl"


@ditto.json
def test_uses_json_when_json_mark_is_applied(snapshot) -> None:
    """The @ditto.json convenience mark selects json format for the snapshot."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".json"


@ditto.yaml
def test_uses_yaml_when_yaml_mark_is_applied(snapshot) -> None:
    """The @ditto.yaml convenience mark selects yaml format for the snapshot."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".yaml"


# --- Raw record marks ---


@ditto.record("pickle")
def test_uses_pickle_when_raw_record_mark_specifies_pickle(snapshot) -> None:
    """The raw @ditto.record mark with 'pickle' selects pickle format."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".pkl"


@ditto.record("json")
def test_uses_json_when_raw_record_mark_specifies_json(snapshot) -> None:
    """The raw @ditto.record mark with 'json' selects json format."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".json"


@ditto.record("yaml")
def test_uses_yaml_when_raw_record_mark_specifies_yaml(snapshot) -> None:
    """The raw @ditto.record mark with 'yaml' selects yaml format."""
    actual = snapshot.filepath("k")

    assert actual.suffix == ".yaml"


# --- Error cases ---


@pytest.mark.xfail(
    reason="multiple record markers", raises=ditto.exceptions.AdditionalMarkError
)
@ditto.record("pickle")
@ditto.record("json")
def test_raises_when_multiple_record_marks_are_applied(snapshot) -> None:
    """Applying more than one record mark to a test raises AdditionalMarkError."""
    snapshot(1, key="a")
