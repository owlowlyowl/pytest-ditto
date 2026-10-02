"""Private, versioned result data. No rendering or Click dependencies."""

from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import msgspec

RESULT_VERSION = 1

Provenance = Literal["disk", "lock", "live", "runtime", "unknown"]


class Identity(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    nodeid: str
    key: str
    recorder: str


class ObjectRef(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    target: str
    storage_key: str
    identity: Identity | None = None


class Metadata(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """Physical bytes/time may be unknown; modified is a POSIX timestamp."""

    size_bytes: int | None = None
    modified: float | None = None
    source: Provenance = "unknown"


class Activity(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    object: ObjectRef
    outcome: Literal[
        "created", "rewritten", "deleted", "proposed", "failed", "accessed", "missing"
    ]
    phase: Literal["read", "write", "delete", "review"]
    reason: str | None = None
    metadata: Metadata = Metadata()


class Coverage(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    target: str
    source: Provenance
    status: Literal["checked", "unchecked", "failed", "unresolved"]
    reason: str | None = None


class InventoryItem(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    object: ObjectRef
    metadata: Metadata
    presence: Literal["present", "unknown", "missing"]


class InventoryResult(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    scope: str
    items: tuple[InventoryItem, ...]
    coverage: tuple[Coverage, ...]


class Check(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    name: str
    outcome: Literal["passed", "failed", "skipped", "unknown"]
    reason: str
    object: ObjectRef | None = None


class LockDelta(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """One exact entry addition/removal; counts have lock-entry units."""

    target: str
    identity: Identity


class LockResult(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    status: Literal["unchanged", "written", "failed", "unknown"] = "unknown"
    added: tuple[LockDelta, ...] = ()
    removed: tuple[LockDelta, ...] = ()
    reason: str | None = None


class TestPhase(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    nodeid: str
    phase: Literal["setup", "call", "teardown"]
    outcome: Literal["passed", "failed", "skipped"]
    expected_failure: bool = False


class TestResult(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    """Passed node IDs describe the call phase, not final teardown outcomes."""

    exit_code: int
    collected: tuple[str, ...] = ()
    passed: tuple[str, ...] = ()
    uncollected: tuple[str, ...] = ()
    deselected: tuple[str, ...] = ()
    phases: tuple[TestPhase, ...] = ()


class OperationResult(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    version: int
    scope: str
    tests: TestResult
    activity: tuple[Activity, ...] = ()
    coverage: tuple[Coverage, ...] = ()
    checks: tuple[Check, ...] = ()
    lock: LockResult = LockResult()
    completeness: Literal["complete", "incomplete", "unsupported"] = "incomplete"
    reason: str | None = None
    scope_kind: Literal["full", "selected", "unknown"] = "unknown"


def safe_location(location: str) -> str:
    """Redact URI secrets without merging targets that differ by public options.

    Never include runtime storage options in results. Unknown backend exception
    messages must be replaced with safe reasons, not copied into artifacts.
    """
    parts = []
    for part in location.split("::"):
        if "://" not in part:
            parts.append(part)
            continue
        try:
            parsed = urlsplit(part)
            netloc = parsed.netloc
            if "@" in netloc:
                auth, _, host = netloc.rpartition("@")
                netloc = (
                    f"{auth.partition(':')[0]}:***@{host}" if ":" in auth else netloc
                )
            query = parse_qsl(parsed.query, keep_blank_values=True)
            masked = [
                (
                    name,
                    "***"
                    if any(
                        word in name.lower()
                        for word in (
                            "password",
                            "passwd",
                            "pwd",
                            "secret",
                            "token",
                            "key",
                            "sig",
                            "credential",
                            "authorization",
                        )
                    )
                    else value,
                )
                for name, value in query
            ]
            parts.append(
                urlunsplit((
                    parsed.scheme,
                    netloc,
                    parsed.path,
                    urlencode(masked, safe="*") if masked != query else parsed.query,
                    "",
                ))
            )
        except ValueError:
            parts.append("<invalid target URI>")
    return "::".join(parts)


def encode_result(result: OperationResult) -> bytes:
    return msgspec.json.encode(result)


def decode_result(data: bytes) -> OperationResult:
    result = msgspec.json.decode(data, type=OperationResult)
    if result.version != RESULT_VERSION:
        raise ValueError("Unsupported Ditto result version")
    return result
