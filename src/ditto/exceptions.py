__all__ = (
    "DittoException",
    "AdditionalMarkError",
    "DittoMarkHasNoIOType",
    "DuplicateSnapshotKeyError",
    "UnknownBackendError",
)


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


class DuplicateSnapshotKeyError(DittoException):
    def __init__(self, key: str) -> None:
        super().__init__(
            f"Snapshot key '{key}' has already been used in this test. "
            "Each snapshot call within a test must use a unique key."
        )


class UnknownBackendError(DittoException):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"No backend registered under the name {name!r}. "
            "Register it via pytest_ditto_register_backends in conftest.py, "
            "a [tool.ditto.backends] entry in pyproject.toml, "
            "or a 'ditto_backends' entry point."
        )
