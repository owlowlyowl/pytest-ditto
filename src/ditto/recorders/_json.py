import json as _json
import math
from pathlib import Path
from typing import Any

from ditto.exceptions import DittoJSONSerializationError

from ._protocol import Recorder


__all__ = ("json",)


def _path_for_key(path: str, key: str) -> str:
    encoded = _json.dumps(key, ensure_ascii=False)
    return f"{path}[{encoded}]"


def _validate_string(value: str, path: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise DittoJSONSerializationError(
            path, "strings must contain valid UTF-8 Unicode"
        ) from exc


def _validate(data: Any, path: str = "$", active: set[int] | None = None) -> None:
    """Validate the strict JSON data model without coercing user values."""
    if active is None:
        active = set()

    data_type = type(data)
    if data is None or data_type is bool or data_type is int:
        return
    if data_type is str:
        _validate_string(data, path)
        return
    if data_type is float:
        if not math.isfinite(data):
            raise DittoJSONSerializationError(path, "floats must be finite")
        return
    if data_type is list:
        identity = id(data)
        if identity in active:
            raise DittoJSONSerializationError(
                path, "cyclic containers are not supported"
            )
        active.add(identity)
        try:
            for index, value in enumerate(data):
                _validate(value, f"{path}[{index}]", active)
        finally:
            active.remove(identity)
        return
    if data_type is dict:
        identity = id(data)
        if identity in active:
            raise DittoJSONSerializationError(
                path, "cyclic containers are not supported"
            )
        active.add(identity)
        try:
            for key, value in data.items():
                if type(key) is not str:
                    raise DittoJSONSerializationError(
                        f"{path}[<key>]", "object keys must be exact built-in strings"
                    )
                _validate_string(key, f"{path}[<key>]")
                _validate(value, _path_for_key(path, key), active)
        finally:
            active.remove(identity)
        return

    raise DittoJSONSerializationError(
        path, "the value has an unsupported type or is a built-in subclass"
    )


def _save(data: Any, filepath: Path) -> None:
    _validate(data)
    text = _json.dumps(
        data,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    )
    filepath.write_bytes(text.encode("utf-8") + b"\n")


def _object_from_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DittoJSONSerializationError(
                "$", "duplicate object keys are not allowed"
            )
        result[key] = value
    return result


def _reject_constant(token: str) -> Any:
    raise DittoJSONSerializationError(
        "$", f"non-finite number token {token} is not allowed"
    )


def _load(filepath: Path) -> Any:
    text = filepath.read_bytes().decode("utf-8", errors="strict")
    data = _json.loads(
        text,
        object_pairs_hook=_object_from_pairs,
        parse_constant=_reject_constant,
    )
    _validate(data)
    return data


json = Recorder(extension="json", save=_save, load=_load)
