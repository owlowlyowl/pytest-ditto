from __future__ import annotations

from ditto.exceptions import (
    AdditionalMarkError,
    DittoAmbiguousTargetError,
    DittoMarkHasNoIOType,
    DittoUnknownRecorderError,
)
from ditto.recorders import Recorder, RECORDER_REGISTRY, default as _default_recorder


__all__ = ("resolve_recorder", "parse_mark_target_selection")


def resolve_recorder(marks: list) -> Recorder:
    """Resolve the recorder from a list of pytest marks.

    Raises
    ------
    AdditionalMarkError
        If more than one `record` mark is present on the test.
    DittoMarkHasNoIOType
        If the mark carries no recorder argument.
    DittoUnknownRecorderError
        If the mark names an unregistered recorder.
    """
    match len(marks):
        case 0:
            return _default_recorder()
        case 1:
            if not marks[0].args:
                raise DittoMarkHasNoIOType()
            name = marks[0].args[0]
            if name not in RECORDER_REGISTRY:
                raise DittoUnknownRecorderError(name, list(RECORDER_REGISTRY))
            return RECORDER_REGISTRY[name]
        case _:
            raise AdditionalMarkError()


def parse_mark_target_selection(marks: list) -> tuple[str | None, str | None]:
    """Return (target_uri, profile_name) from the record mark.

    At most one of the two values is non-None. Raises
    `DittoAmbiguousTargetError` if both `target=` and `target_profile=` appear
    on the same mark.
    """
    if not marks:
        return None, None

    kwargs = marks[0].kwargs
    target_uri: str | None = kwargs.get("target")
    profile_name: str | None = kwargs.get("target_profile")

    if target_uri is not None and profile_name is not None:
        raise DittoAmbiguousTargetError(
            "Use either target= or target_profile=, not both."
        )

    return target_uri, profile_name
