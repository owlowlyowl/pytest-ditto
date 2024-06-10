__all__ = (
    "DittoException",
    "AdditionalMarkError",
    "DittoMarkHasNoIOType",
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
