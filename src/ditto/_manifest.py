"""The introspection manifest: the inventory shape for CLI rendering.

Written by the in-pytest introspection pass. Carries only enumerated metadata,
never credentials.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ManifestEntry:
    """One stored snapshot.

    `size_bytes` is the byte size when known, or `None` when the inventory was
    read credential-free from `ditto.lock` (a remote snapshot whose physical size
    needs `--live`). `modified` is a POSIX timestamp when the backend reports one
    (local files, S3), else `None`.
    """

    storage_key: str
    size_bytes: int | None
    modified: float | None


@dataclass(frozen=True)
class BackendManifest:
    """The snapshots under one resolved backend, keyed by its canonical URI."""

    location: str
    entries: list[ManifestEntry]


# The whole inventory for one CLI invocation: one BackendManifest per resolved
# backend. A plain list — there is no inventory-level data to justify a wrapper.
Manifest = list[BackendManifest]


def to_json(backends: Manifest) -> str:
    """Serialize a manifest to a JSON string."""
    return json.dumps([asdict(b) for b in backends])


def from_json(text: str) -> Manifest:
    """Deserialize a manifest from a JSON string."""
    return [
        BackendManifest(
            location=b["location"],
            entries=[ManifestEntry(**e) for e in b["entries"]],
        )
        for b in json.loads(text)
    ]
