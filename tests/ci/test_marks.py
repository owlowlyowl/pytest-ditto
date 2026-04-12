import pytest

import ditto


# --- Default behaviour ---


def test_defaults_to_pickle_when_no_mark_is_applied(snapshot) -> None:
    """Without a record mark, the snapshot fixture uses pickle format."""
    actual = snapshot.recorder.extension

    assert actual == "pkl"


# --- Convenience marks ---


@ditto.pickle
def test_uses_pickle_when_pickle_mark_is_applied(snapshot) -> None:
    """The @ditto.pickle convenience mark selects pickle format for the snapshot."""
    actual = snapshot.recorder.extension

    assert actual == "pkl"


@ditto.json
def test_uses_json_when_json_mark_is_applied(snapshot) -> None:
    """The @ditto.json convenience mark selects json format for the snapshot."""
    actual = snapshot.recorder.extension

    assert actual == "json"


@ditto.yaml
def test_uses_yaml_when_yaml_mark_is_applied(snapshot) -> None:
    """The @ditto.yaml convenience mark selects yaml format for the snapshot."""
    actual = snapshot.recorder.extension

    assert actual == "yaml"


# --- Raw record marks ---


@ditto.record("pickle")
def test_uses_pickle_when_raw_record_mark_specifies_pickle(snapshot) -> None:
    """The raw @ditto.record mark with 'pickle' selects pickle format."""
    actual = snapshot.recorder.extension

    assert actual == "pkl"


@ditto.record("json")
def test_uses_json_when_raw_record_mark_specifies_json(snapshot) -> None:
    """The raw @ditto.record mark with 'json' selects json format."""
    actual = snapshot.recorder.extension

    assert actual == "json"


@ditto.record("yaml")
def test_uses_yaml_when_raw_record_mark_specifies_yaml(snapshot) -> None:
    """The raw @ditto.record mark with 'yaml' selects yaml format."""
    actual = snapshot.recorder.extension

    assert actual == "yaml"


# --- Error cases ---


@pytest.mark.xfail(
    reason="multiple record markers", raises=ditto.exceptions.AdditionalMarkError
)
@ditto.record("pickle")
@ditto.record("json")
def test_raises_when_multiple_record_marks_are_applied(snapshot) -> None:
    """Applying more than one record mark to a test raises AdditionalMarkError."""
    snapshot(1, key="a")


@pytest.mark.xfail(
    reason="unregistered recorder name", raises=ditto.exceptions.DittoMarkHasNoIOType
)
@ditto.record("nonexistent-format")
def test_raises_when_record_mark_specifies_unknown_recorder(snapshot) -> None:
    """Specifying an unregistered recorder name raises DittoMarkHasNoIOType."""
    pass


# --- target resolution ---


def test_target_relative_file_uri_resolves_to_nested_test_dir(pytester) -> None:
    """A relative `file://` target resolves relative to the test file."""
    subdir = pytester.mkdir("nested")
    subdir.joinpath("test_inner.py").write_text(
        "import ditto\n\n"
        "@ditto.record('json', target='file://.custom')\n"
        "def test_inner(snapshot):\n"
        "    assert snapshot(42, key='x') == 42\n"
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert (subdir / ".custom").is_dir()
    assert list((subdir / ".custom").glob("*.json"))
    assert not (pytester.path / ".custom").exists()


def test_target_absolute_file_uri_uses_given_path(pytester, tmp_path) -> None:
    """An absolute `file://` target stores snapshots at the requested path."""
    target_dir = tmp_path / "snaps"
    pytester.makepyfile(
        f"""
        import ditto

        @ditto.record("json", target="file://{target_dir.as_posix()}")
        def test_inner(snapshot):
            assert snapshot(99, key="y") == 99
        """
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert target_dir.is_dir()
    assert list(target_dir.glob("*.json"))


def test_target_memory_uri_round_trips_without_creating_dot_ditto(pytester) -> None:
    """A `memory://` target round-trips in process and does not create `.ditto`."""
    pytester.makepyfile(
        """
        import ditto

        @ditto.record("json", target="memory://")
        def test_inner(snapshot):
            assert snapshot({"a": 1}, key="z") == {"a": 1}
        """
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert not (pytester.path / ".ditto").exists()


def test_mark_target_overrides_ditto_target_ini(pytester, tmp_path) -> None:
    """A mark `target=` takes precedence over `ditto_target` in config."""
    mark_dir = tmp_path / "mark-snaps"
    ini_dir = tmp_path / "ini-snaps"
    pytester.makeini(
        f"""
        [pytest]
        ditto_target = file://{ini_dir.as_posix()}
        """
    )
    pytester.makepyfile(
        f"""
        import ditto

        @ditto.record("json", target="file://{mark_dir.as_posix()}")
        def test_inner(snapshot):
            assert snapshot(1, key="k") == 1
        """
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert mark_dir.is_dir()
    assert not ini_dir.exists()


def test_ditto_target_ini_applies_when_no_mark_is_present(pytester) -> None:
    """Without a mark, `ditto_target` provides the project-wide default target."""
    pytester.makeini(
        """
        [pytest]
        ditto_target = file://.snapshots
        """
    )
    subdir = pytester.mkdir("sub")
    subdir.joinpath("test_inner.py").write_text(
        "def test_inner(snapshot):\n"
        "    assert snapshot(7, key='n') == 7\n"
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert (subdir / ".snapshots").is_dir()
    assert not (pytester.path / ".snapshots").exists()


def test_default_target_falls_back_to_dot_ditto(pytester) -> None:
    """Without a mark or config, the fixture falls back to `file://.ditto`."""
    pytester.makepyfile(
        """
        def test_inner(snapshot):
            assert snapshot(7, key="n") == 7
        """
    )

    result = pytester.runpytest()

    result.assert_outcomes(passed=1)
    assert (pytester.path / ".ditto").is_dir()
    assert list((pytester.path / ".ditto").glob("*.pkl"))


def test_unknown_target_scheme_raises_value_error(pytester) -> None:
    """An unrecognised target scheme raises a helpful `ValueError`."""
    pytester.makepyfile(
        """
        import ditto

        @ditto.record("json", target="notascheme://something")
        def test_inner(snapshot):
            snapshot(1, key="k")
        """
    )

    result = pytester.runpytest()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*Unknown backend scheme*notascheme*"])
