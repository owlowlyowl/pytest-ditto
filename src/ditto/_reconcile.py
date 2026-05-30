from __future__ import annotations

import msgspec

__all__ = ("ReconcileResult", "owned_prefixes", "diff_backend")


class ReconcileResult(msgspec.Struct, frozen=True):
    """Drift between a backend and the lock, scoped to owned prefixes.

    Attributes
    ----------
    missing : tuple[str, ...]
        Storage keys present in the lock but absent from the backend.
    orphan : tuple[str, ...]
        Storage keys present in the backend, under an owned prefix, with no lock
        entry. The caller may further classify these (e.g. created this run vs
        genuinely stale) for reporting.
    """

    missing: tuple[str, ...]
    orphan: tuple[str, ...]


def owned_prefixes(modules: set[str], scheme: str) -> frozenset[str]:
    """Return the storage-key prefixes owned by `modules` for `scheme`.

    File backends use a flat dotted prefix (`module.`); all other schemes use a
    slash-separated prefix (`module/`). Mirrors the live key derivation.
    """
    if scheme == "file":
        return frozenset(m.replace("/", ".") + "." for m in modules)
    return frozenset(m + "/" for m in modules)


def diff_backend(
    lock_keys: set[str], backend_keys: set[str], owned: frozenset[str]
) -> ReconcileResult:
    """Diff a backend's keys against the lock's keys, scoped to owned prefixes.

    `missing` is every lock key absent from the backend. `orphan` is every
    backend key that falls under an owned prefix and has no lock entry; backend
    keys outside the owned prefixes (another suite or branch on a shared backend)
    are never reported.
    """
    missing = tuple(sorted(lock_keys - backend_keys))
    orphan = tuple(
        sorted(
            k
            for k in backend_keys
            if k not in lock_keys and any(k.startswith(p) for p in owned)
        )
    )
    return ReconcileResult(missing=missing, orphan=orphan)
