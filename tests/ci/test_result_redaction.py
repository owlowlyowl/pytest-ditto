from __future__ import annotations

from ditto._result_policy import redact_targets, target_coverage
from ditto._results import (
    RESULT_VERSION,
    Activity,
    Check,
    Coverage,
    Identity,
    LockDelta,
    LockResult,
    ObjectRef,
    OperationResult,
    TestResult as RunTests,
)


def test_keeps_each_target_when_masked_locations_coincide() -> None:
    """Targets that differ only by a secret stay separate entries."""
    first = "memory://host/snaps?token=one"
    second = "memory://host/snaps?token=two"
    observed = {first: Coverage(first, "live", "failed", "OSError inspecting target")}

    coverage = target_coverage(observed, {first, second}, set())
    actual = [(item.target, item.status) for item in coverage]

    expected = [(first, "failed"), (second, "unchecked")]
    assert actual == expected


def test_masks_every_target_when_result_is_redacted() -> None:
    """Redaction reaches activity, coverage, checks and lock deltas alike."""
    target = "memory://alice:pw@host/snaps"
    identity = Identity("t.py::test_x", "k", "json")
    ref = ObjectRef(target, "t.test_x@k.json", identity)
    result = OperationResult(
        RESULT_VERSION,
        "/project",
        RunTests(0),
        (Activity(ref, "created", "write"),),
        (Coverage(target, "runtime", "unchecked"),),
        (Check("missing", "failed", "Recorded object absent", ref, target),),
        LockResult("written", (LockDelta(target, identity),), ()),
    )

    redacted = redact_targets(result)
    actual = {
        redacted.activity[0].object.target,
        redacted.coverage[0].target,
        redacted.checks[0].object.target,
        redacted.checks[0].target,
        redacted.lock.added[0].target,
    }

    expected = {"memory://alice:***@host/snaps"}
    assert actual == expected
