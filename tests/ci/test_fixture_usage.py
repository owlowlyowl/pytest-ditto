import pytest

import ditto


def test_exception_raised_when_no_key_specified(snapshot):
    with pytest.raises(TypeError) as excinfo:
        snapshot(1)
    assert excinfo.match(
        r"^Snapshot.__call__().*missing 1 required positional argument: 'key'"
    )
