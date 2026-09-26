from __future__ import annotations

import warnings
from collections.abc import Mapping, MutableMapping
from pathlib import Path

from ditto.backends import FsspecMapping
from ditto._manifest import BackendManifest, ManifestEntry, to_json
from ditto.exceptions import DittoWarning


__all__ = ("write_introspect_manifest",)


def _enumerate_entries(backend: MutableMapping[str, bytes]) -> list[ManifestEntry]:
    """Enumerate one backend's stored snapshots as manifest entries.

    fsspec-backed stores report size and mtime from a single listing; generic
    MutableMapping backends (e.g. Redis) report size via a per-key read and
    carry no mtime. Enumeration errors are warned and yield an empty backend, so
    one unreachable store never aborts the whole pass — the backend still appears
    in the manifest (so the CLI can flag it as empty/misconfigured).
    """
    try:
        if isinstance(backend, FsspecMapping):
            return [
                ManifestEntry(storage_key=key, size_bytes=size, modified=modified)
                for key, size, modified in backend.stat_entries()
            ]
        return [
            ManifestEntry(storage_key=key, size_bytes=len(backend[key]), modified=None)
            for key in backend
        ]
    except Exception as exc:
        warnings.warn(
            f"Failed to enumerate backend {backend!r}: {exc}; "
            "reporting it with no entries.",
            category=DittoWarning,
            stacklevel=1,
        )
        return []


def write_introspect_manifest(
    path: str, backends: Mapping[str, MutableMapping[str, bytes]]
) -> None:
    """Write a manifest of every resolved backend to `path`.

    Called before the session ExitStack closes, so backends are still open.
    """
    manifest = [
        BackendManifest(location=uri, entries=_enumerate_entries(backend))
        for uri, backend in backends.items()
    ]
    Path(path).write_text(to_json(manifest))
