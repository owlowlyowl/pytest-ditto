import pytest

import ditto


@pytest.fixture(scope="module")
def _module_scoped_data(snapshot) -> int:
    return snapshot(1, key="data")


@pytest.mark.xfail(
    reason="snapshot is function-scoped; module-scoped fixtures cannot request it."
)
@ditto.yaml
def test_fails_when_module_scoped_fixture_uses_snapshot(
    snapshot, _module_scoped_data
) -> None:
    """A module-scoped fixture cannot request the function-scoped snapshot fixture."""
    result = _module_scoped_data + 34

    assert result == snapshot(result, key="result")
