from __future__ import annotations

import msgspec
import pytest

from ditto._results import (
    RESULT_VERSION,
    Activity,
    Coverage,
    Identity,
    LockDelta,
    LockResult,
    Metadata,
    ObjectRef,
    OperationResult,
    TestResult as RunTests,
    decode_result,
    encode_result,
)


def test_preserves_evidence_when_result_is_serialized() -> None:
    """Serialization preserves exact identities and observed outcomes."""
    identity = Identity("tests/t.py::test_x[a::b]", "[bold]body:raw", "custom.json")
    result = OperationResult(
        RESULT_VERSION,
        "/project",
        RunTests(1, (identity.nodeid,), (identity.nodeid,)),
        (
            Activity(
                ObjectRef("local", "hashed.json", identity),
                "rewritten",
                "write",
                metadata=Metadata(19, None, "runtime"),
            ),
            Activity(
                ObjectRef("archive", "hashed.json", identity),
                "failed",
                "delete",
                "PermissionError",
            ),
        ),
        (Coverage("archive", "live", "failed", "Unavailable"),),
        lock=LockResult("written", (), (LockDelta("local", identity),)),
        completeness="incomplete",
    )

    actual = decode_result(encode_result(result))
    expected = result

    assert actual == expected


@pytest.mark.parametrize(
    "data",
    [
        b'{"version":999,"scope":"x","tests":{"exit_code":0}}',
        b'{"version":1,"scope":"x","tests":{"exit_code":"ok"}}',
        b'{"version":1,"scope":"x"}',
        b'{"version":1,"scope":"x","tests":{"exit_code":0,"extra":1}}',
        b"[]",
        b"{",
    ],
)
def test_rejects_handoff_when_schema_is_invalid(data: bytes) -> None:
    """Invalid handoffs cannot establish a successful operation."""
    with pytest.raises((ValueError, msgspec.ValidationError)):
        decode_result(data)
