from __future__ import annotations

import pytest

pytest.importorskip("ditto_pandas")

import ditto  # noqa: E402

pd = pytest.importorskip("pandas")


def build_monthly_sales_frame() -> object:
    return pd.DataFrame({
        "region": ["north", "south", "west"],
        "orders": [12, 8, 5],
        "revenue": [1200.0, 910.5, 640.25],
    })


@ditto.pandas.json(target_profile="postgres_frames")
def test_round_trips_dataframe_when_mark_uses_named_postgres_profile(
    snapshot,
) -> None:
    """A named Postgres target profile replays a stored dataframe on later runs."""
    expected = build_monthly_sales_frame()

    actual = snapshot(expected, key="monthly_sales")

    pd.testing.assert_frame_equal(actual, expected)
