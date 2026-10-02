"""Adapt error-aware manifests without deriving identities from file labels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ._credentials import mask_credentials
from ._lockfile import LockEntry
from ._inventory import location_key
from ._manifest import BackendManifest
from ._results import (
    Coverage,
    Identity,
    InventoryItem,
    InventoryResult,
    Metadata,
    ObjectRef,
    Provenance,
)


def inventory_result(
    manifest: Sequence[BackendManifest],
    scope: str,
    sources: Mapping[str, Provenance],
    identities: Mapping[tuple[str, str], LockEntry],
) -> InventoryResult:
    """Sources are supplied by discovery, never guessed from unknown metadata.

    Identity lookup uses the original target and key before location redaction.
    An unknown/unavailable source cannot establish physical presence.
    """
    locations = {
        target: location_key(target)
        for target in {backend.location for backend in manifest}
        | {target for target, _ in identities}
    }
    return inventory_evidence(manifest, scope, sources, identities, locations)


def inventory_evidence(
    manifest: Sequence[BackendManifest],
    scope: str,
    sources: Mapping[str, Provenance],
    identities: Mapping[tuple[str, str], LockEntry],
    locations: Mapping[str, str],
) -> InventoryResult:
    """Combine manifest evidence using locations normalized at the I/O boundary."""
    owners = {
        (locations[target], key): owner for (target, key), owner in identities.items()
    }
    items = []
    coverage = []
    for backend in manifest:
        location = mask_credentials(backend.location)
        source = sources.get(backend.location, "unknown")
        coverage.append(backend_coverage(backend, source))
        # Error entries are unknown, never an empty successful inventory.
        if backend.error is not None:
            continue
        for entry in backend.entries:
            owner = owners.get((locations[backend.location], entry.storage_key))
            identity = (
                Identity(owner.nodeid, owner.key, owner.recorder) if owner else None
            )
            items.append(
                InventoryItem(
                    ObjectRef(location, entry.storage_key, identity),
                    Metadata(entry.size_bytes, entry.modified, source),
                    "present" if source in ("disk", "live") else "unknown",
                )
            )
    return InventoryResult(scope, tuple(items), tuple(coverage))


def backend_coverage(backend: BackendManifest, source: Provenance) -> Coverage:
    """Distinguish failed enumeration from empty or unexamined inventories."""
    location = mask_credentials(backend.location)
    if backend.error is not None:
        return Coverage(
            location,
            source,
            "failed",
            "Backend inventory failed; details remain in the source diagnostic",
        )
    if source in ("disk", "live"):
        return Coverage(location, source, "checked")
    return Coverage(location, source, "unchecked", "Physical inventory not checked")
