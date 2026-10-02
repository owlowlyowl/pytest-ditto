"""Adapt error-aware manifests without deriving identities from file labels."""

from __future__ import annotations

from collections.abc import Mapping

from ._lockfile import LockEntry
from ._manifest import Manifest
from ._results import (
    Coverage,
    Identity,
    InventoryItem,
    InventoryResult,
    Metadata,
    ObjectRef,
    safe_location,
)


def inventory_result(
    manifest: Manifest,
    scope: str,
    sources: Mapping[str, str],
    identities: Mapping[tuple[str, str], LockEntry],
) -> InventoryResult:
    """Sources are supplied by discovery, never guessed from unknown metadata.

    Identity lookup uses the original target and key before location redaction.
    An unknown/unavailable source cannot establish physical presence.
    """
    # Match both local filesystem locations and canonical file:// URIs to the
    # existing lock identity index. Never parse a hashed filename for identity.
    from ._inventory import location_key

    owners = {
        (location_key(target), key): owner
        for (target, key), owner in identities.items()
    }
    items = []
    coverage = []
    for backend in manifest:
        location = safe_location(backend.location)
        source = sources.get(backend.location, "unknown")
        if source not in ("disk", "lock", "live", "runtime", "unknown"):
            raise ValueError("Invalid inventory provenance")
        # msgspec Literals are validated on decode; build explicit branches for
        # type checkers rather than coercing arbitrary supplied strings.
        provenance = (
            "disk"
            if source == "disk"
            else "lock"
            if source == "lock"
            else "live"
            if source == "live"
            else "runtime"
            if source == "runtime"
            else "unknown"
        )
        reason = "Backend inventory failed; details remain in the source diagnostic"
        coverage.append(
            Coverage(
                location,
                provenance,
                "failed"
                if backend.error is not None
                else "checked"
                if source in ("disk", "live")
                else "unchecked",
                reason
                if backend.error is not None
                else "Physical inventory not checked"
                if source not in ("disk", "live")
                else None,
            )
        )
        # Error entries are unknown, never an empty successful inventory.
        if backend.error is not None:
            continue
        for entry in backend.entries:
            owner = owners.get((location_key(backend.location), entry.storage_key))
            identity = (
                Identity(owner.nodeid, owner.key, owner.recorder) if owner else None
            )
            items.append(
                InventoryItem(
                    ObjectRef(location, entry.storage_key, identity),
                    Metadata(entry.size_bytes, entry.modified, provenance),
                    "present" if source in ("disk", "live") else "unknown",
                )
            )
    return InventoryResult(scope, tuple(items), tuple(coverage))
