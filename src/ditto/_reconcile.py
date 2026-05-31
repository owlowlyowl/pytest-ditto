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
        Backend keys under an owned prefix, absent from the lock, NOT produced
        this run — safe to delete.
    unsynced : tuple[str, ...]
        Keys produced this run but absent from the lock (the lock is out of date).
        Never deleted by prune; reported so the user runs `ditto lock`.
    """

    missing: tuple[str, ...]
    orphan: tuple[str, ...]
    unsynced: tuple[str, ...]


def owned_prefixes(modules: set[str], scheme: str) -> frozenset[str]:
    """Return the storage-key prefixes owned by `modules` for `scheme`.

    File backends use a flat dotted prefix (`module.`); all other schemes use a
    slash-separated prefix (`module/`). Mirrors the live key derivation.
    """
    if scheme == "file":
        return frozenset(m.replace("/", ".") + "." for m in modules)
    return frozenset(m + "/" for m in modules)


def diff_backend(
    lock_keys: set[str],
    backend_keys: set[str],
    owned: frozenset[str],
    created_keys: set[str],
) -> ReconcileResult:
    """Classify a target's drift against the lock, scoped to owned prefixes.

    `missing` = lock keys absent from the backend. `unsynced` = keys created this
    run that the lock does not record. `orphan` = backend keys under an owned
    prefix, absent from the lock, that were NOT created this run (deletable).
    Keys outside the owned prefixes (another suite/branch on a shared backend) are
    never reported.
    """
    missing = tuple(sorted(lock_keys - backend_keys))
    drift = {
        k
        for k in backend_keys
        if k not in lock_keys and any(k.startswith(p) for p in owned)
    }
    unsynced = created_keys - lock_keys
    orphan = tuple(sorted(drift - unsynced))
    return ReconcileResult(
        missing=missing, orphan=orphan, unsynced=tuple(sorted(unsynced))
    )
