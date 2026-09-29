__all__ = (
    "DittoException",
    "DittoWarning",
    "AdditionalMarkError",
    "DittoMarkHasNoIOType",
    "DittoUnknownRecorderError",
    "DittoRecorderLoadError",
    "DittoRecorderConflictError",
    "DittoBackendLoadError",
    "DittoBackendConflictError",
    "DittoBackendChangedError",
    "DittoJSONSerializationError",
    "DuplicateSnapshotKeyError",
    "DittoSnapshotNameCollisionError",
    "DittoSnapshotNameTooLongError",
    "DittoAmbiguousTargetError",
    "DittoUnknownProfileError",
    "DittoInvalidProfileError",
    "DittoDuplicateProfileError",
    "DittoLockFileError",
    "DittoLockFileVersionError",
    "DittoUnhashableStorageOptionsError",
)


class DittoWarning(UserWarning):
    """Category for all pytest-ditto advisory warnings.

    Subclasses `UserWarning`, so a blanket `ignore::UserWarning` still applies;
    use `ignore::ditto.exceptions.DittoWarning` to silence only ditto's
    advisories, or `error::ditto.exceptions.DittoWarning` to escalate them.
    """


class DittoException(Exception):
    pass


class AdditionalMarkError(DittoException):
    def __init__(self) -> None:
        super().__init__("Only one record mark is allowed per test.")


class DittoMarkHasNoIOType(DittoException):
    def __init__(self) -> None:
        _msg = (
            "The ditto record mark has no associated IO type. "
            "This is most likely an implementation issue with the mark being used. "
            "The IO type is assumed to be the first argument of the `mark.args`."
        )
        super().__init__(_msg)


class DittoUnknownRecorderError(DittoException):
    """Raised when a requested recorder is not installed."""

    def __init__(self, name: str, available: list[str]) -> None:
        available_str = ", ".join(sorted(available)) if available else "(none)"
        super().__init__(
            f"Unknown ditto recorder {name!r}. Available recorders: {available_str}."
        )


class DittoRecorderLoadError(DittoException):
    """Raised when an installed recorder's entry point fails to load."""

    def __init__(
        self, name: str, distribution: str, cause: BaseException, hint: str = ""
    ) -> None:
        message = (
            f"ditto recorder {name!r} from {distribution} failed to load: "
            f"{type(cause).__name__}: {cause}"
        )
        super().__init__(f"{message}. {hint}" if hint else message)


class DittoRecorderConflictError(DittoException):
    """Raised when a recorder registration breaks the plugin contract.

    Raised when a conflicted recorder is looked up, and when `register` is
    given a name that would conflict. The message describes the conflict and
    names the distributions involved.
    """


class DittoBackendLoadError(DittoException):
    """Raised when an installed backend's entry point fails to load."""

    def __init__(self, scheme: str, distribution: str, cause: BaseException) -> None:
        super().__init__(
            f"ditto backend {scheme!r} from {distribution} failed to load: "
            f"{type(cause).__name__}: {cause}"
        )


class DittoBackendConflictError(DittoException):
    """Raised when a backend registration breaks the plugin contract.

    Raised when a conflicted scheme is looked up. The message describes the
    conflict and names the distributions involved.
    """


class DittoBackendChangedError(DittoException):
    """Raised when a target's backend would change partway through a session.

    ditto treats a target URI as one store in the lock, `verify` and `prune`,
    so every backend for a target in a session must come from the same factory.
    """

    def __init__(self, scheme: str, uri: str) -> None:
        super().__init__(
            f"The backend for {scheme!r} changed after {uri} was first used in "
            "this session. ditto builds every backend for a target with the same "
            "factory for the whole session, so set BACKEND_REGISTRY.overrides "
            "before any test uses the scheme, for example in a session-scoped "
            "fixture, or give the test a target of its own."
        )


class DittoJSONSerializationError(DittoException):
    """Raised for values outside ditto's strict JSON data model."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(
            f"Strict JSON rejected the value at {path}: {detail}. "
            "Use only exact built-in None, bool, int, finite float, str, list, "
            "and dict values with exact string keys, or select another recorder."
        )


class DuplicateSnapshotKeyError(DittoException):
    def __init__(self, key: str) -> None:
        super().__init__(
            f"Snapshot key '{key}' has already been used in this test. "
            "Each snapshot call within a test must use a unique key."
        )


class DittoSnapshotNameCollisionError(DittoException):
    """Raised when two different snapshots would be stored under one name.

    A stored name ends in a short hash of the snapshot's identity, so this
    needs two snapshots whose readable labels and hashes both match.
    """

    def __init__(self, storage_key: str, first: str, second: str) -> None:
        super().__init__(
            f"Snapshots {first!r} and {second!r} would both be stored as "
            f"{storage_key!r}. Change one of their keys or parametrize IDs."
        )


class DittoSnapshotNameTooLongError(DittoException):
    """Raised when a test module's path leaves no room for a snapshot's name.

    A `file://` snapshot's name starts with the module path, dotted, and must
    fit in the file system's limit for a file name.
    """

    def __init__(self, module: str, limit: int) -> None:
        super().__init__(
            f"The test module path {module!r} is too long to name its snapshots "
            f"within {limit} bytes. Use a shorter path for the test file."
        )


class DittoAmbiguousTargetError(DittoException):
    def __init__(self, context: str) -> None:
        super().__init__(context)


class DittoUnknownProfileError(DittoException):
    def __init__(self, name: str, available: list[str]) -> None:
        available_str = ", ".join(sorted(available)) if available else "(none)"
        super().__init__(
            f"Unknown ditto target profile {name!r}. "
            f"Available profiles: {available_str}."
        )


class DittoInvalidProfileError(DittoException):
    def __init__(self, name: str, detail: str | None = None) -> None:
        message = detail or "expected a URI string or mapping with a 'uri' field."
        super().__init__(f"Invalid ditto target profile {name!r}: {message}")


class DittoDuplicateProfileError(DittoException):
    def __init__(self, names: list[str]) -> None:
        duplicates = ", ".join(sorted(names))
        super().__init__(
            f"Duplicate ditto target profile name(s) defined in both "
            f"ditto_target_profiles fixture and pyproject.toml: {duplicates}."
        )


class DittoLockFileError(DittoException):
    def __init__(self, detail: str) -> None:
        super().__init__(f"Could not read ditto.lock: {detail}")


class DittoLockFileVersionError(DittoLockFileError):
    def __init__(self, expected: int, got: object) -> None:
        super().__init__(
            f"unsupported lock-file version {got!r}; expected {expected}. "
            "Upgrade pytest-ditto."
        )


class DittoUnhashableStorageOptionsError(DittoException):
    """Raised when `ditto_storage_options` contains an unhashable value."""

    def __init__(self, value: object) -> None:
        super().__init__(
            f"ditto_storage_options contains an unhashable value ({value!r}, "
            f"type {type(value).__name__}). Backend cache identity requires every "
            "storage option to be hashable: two resolutions of the same logical "
            "target would otherwise silently get separate backend instances, "
            "breaking session-lifecycle tracking (prune, lock) for that target. "
            "Pass a hashable equivalent, or wrap the value so identity can be "
            "established some other way."
        )
