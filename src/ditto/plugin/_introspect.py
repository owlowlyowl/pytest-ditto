from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from pathlib import Path

from ditto.backends import FsspecMapping
from ditto._manifest import BackendManifest, ManifestEntry, to_json


__all__ = ("write_introspect_manifest",)


def _enumerate_backend(
    location: str, backend: MutableMapping[str, bytes]
) -> BackendManifest:
    """Enumerate one backend's stored snapshots into its manifest.

    fsspec-backed stores report size and mtime from a single listing; generic
    MutableMapping backends (e.g. Redis) report size via a per-key read and
    carry no mtime. A backend that can't be enumerated is recorded with the
    error instead of entries, so one unreachable store neither aborts the pass
    nor passes for an empty one.
    """
    try:
        if isinstance(backend, FsspecMapping):
            entries = [
                ManifestEntry(storage_key=key, size_bytes=size, modified=modified)
                for key, size, modified in backend.stat_entries()
            ]
        else:
            entries = [
                ManifestEntry(
                    storage_key=key, size_bytes=len(backend[key]), modified=None
                )
                for key in backend
            ]
    except Exception as exc:
        return BackendManifest(location=location, entries=[], error=str(exc))
    return BackendManifest(location=location, entries=entries)


def write_introspect_manifest(
    path: str, backends: Mapping[str, MutableMapping[str, bytes]]
) -> None:
    """Write a manifest of every resolved backend to `path`.

    Called before the session ExitStack closes, so backends are still open.
    """
    manifest = [_enumerate_backend(uri, backend) for uri, backend in backends.items()]
    Path(path).write_text(to_json(manifest))
