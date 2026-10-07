"""Which snapshots `ditto list --test` selects by their lock node id."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from rich.console import Console

from ditto.cli._data import nodeid_selected
from ditto.cli._inventory import cmd_list


NODEID = "tests/ci/test_api.py::TestOrders::test_totals[eu]"


@pytest.mark.parametrize(
    "selector",
    [
        NODEID,
        "tests",
        "tests/ci/",
        "tests/ci/test_api.py",
        "tests/ci/test_api.py::TestOrders",
        "tests/ci/test_api.py::TestOrders::test_totals",
    ],
    ids=["exact", "dir", "dir-slash", "file", "class", "parametrized-test"],
)
def test_selects_a_node_id_by_itself_or_a_boundary_prefix(selector: str) -> None:
    """A selector matches its exact node id or a prefix ending at /, :: or [."""
    assert nodeid_selected(NODEID, [selector])


@pytest.mark.parametrize(
    "selector",
    [
        "tests/c",
        "tests/ci/test_ap",
        "tests/ci/test_api.py::TestOrd",
        "tests/ci/test_api.py::TestOrders::test_total",
        "test_api.py",
        "tests/ci/test_api.py::TestOrders::test_totals[us]",
        "",
    ],
    ids=[
        "partial-dir",
        "partial-file",
        "partial-class",
        "partial-test",
        "substring",
        "other-case",
        "empty",
    ],
)
def test_does_not_select_a_node_id_by_substring(selector: str) -> None:
    """A selector that stops mid-name, or isn't a prefix at all, matches nothing."""
    assert not nodeid_selected(NODEID, [selector])


def test_selects_a_node_id_when_any_selector_matches() -> None:
    """Several selectors are alternatives: one match selects the node id."""
    assert nodeid_selected(NODEID, ["tests/other.py", "tests/ci/test_api.py"])


TWO_FILES = {
    "test_orders": """
        import pytest

        @pytest.mark.parametrize("region", ["eu", "us"])
        def test_totals(snapshot, region):
            snapshot(1, key="subtotal")
    """,
    "test_refunds": """
        def test_refund(snapshot):
            snapshot(1, key="response")
    """,
}


def _list(pytester, *args: str):
    return CliRunner().invoke(
        cmd_list, [str(pytester.path), *args], obj=Console(width=200)
    )


def test_list_shows_only_snapshots_of_the_selected_tests(pytester) -> None:
    """--test keeps the snapshots whose test it selects and drops the rest."""
    pytester.makepyfile(**TWO_FILES)
    pytester.runpytest_subprocess().assert_outcomes(passed=3)

    result = _list(pytester, "--test", "test_orders.py::test_totals[eu]")

    assert result.exit_code == 0, result.output
    assert "test_orders.py::test_totals[eu]" in result.output
    assert "test_totals[us]" not in result.output
    assert "test_refund" not in result.output


def test_list_shows_snapshots_of_any_selected_test(pytester) -> None:
    """Repeated --test options select the snapshots of either test."""
    pytester.makepyfile(**TWO_FILES)
    pytester.runpytest_subprocess().assert_outcomes(passed=3)

    result = _list(
        pytester, "--test", "test_refunds.py", "--test", "test_orders.py::test_totals"
    )

    assert result.exit_code == 0, result.output
    assert "test_refunds.py::test_refund" in result.output
    assert "test_totals[eu]" in result.output
    assert "test_totals[us]" in result.output


def test_list_exits_one_when_no_snapshot_matches_the_test(pytester) -> None:
    """A --test that selects nothing lists nothing and exits 1, like an empty list."""
    pytester.makepyfile(**TWO_FILES)
    pytester.runpytest_subprocess().assert_outcomes(passed=3)

    result = _list(pytester, "--test", "test_orders.py::test_tot")

    assert result.exit_code == 1
    assert "test_orders.py" not in result.output


def test_list_says_how_many_snapshots_the_lock_does_not_record(pytester) -> None:
    """A snapshot the lock doesn't record has no node id; --test says it skipped it."""
    pytester.makepyfile(**TWO_FILES)
    pytester.runpytest_subprocess().assert_outcomes(passed=3)
    (
        pytester.path / ".ditto" / "test_orders.test_old@v~0123abcd0123abcd.json"
    ).write_text("1")

    result = _list(pytester, "--test", "test_orders.py")

    assert result.exit_code == 0, result.output
    assert "test_old" not in result.output
    assert "Left out 1 snapshot that ditto.lock doesn't record" in result.output
