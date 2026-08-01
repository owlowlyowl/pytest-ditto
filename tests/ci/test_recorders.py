import json as _json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
import yaml as _yaml

from ditto import recorders
from ditto.exceptions import DittoJSONSerializationError


json_recorder = recorders.get("json")
yaml_recorder = recorders.get("yaml")


@pytest.mark.parametrize("recorder", [json_recorder, yaml_recorder])
def test_recorder_saves_file_to_disk(tmp_path: Path, recorder) -> None:
    filepath = tmp_path / f"tmp.{recorder.extension}"

    recorder.save(1, filepath)

    assert filepath.exists()


@pytest.mark.parametrize(
    "data",
    [
        None,
        False,
        True,
        0,
        -42,
        1.25,
        "snowman: ☃",
        [],
        {},
        {"nested": [None, True, -1, 2.5, "x", {"leaf": []}]},
    ],
)
def test_json_roundtrip_accepts_strict_data_model(tmp_path: Path, data) -> None:
    filepath = tmp_path / "snapshot.json"

    json_recorder.save(data, filepath)

    assert json_recorder.load(filepath) == data


def test_json_accepts_shared_acyclic_containers(tmp_path: Path) -> None:
    shared = [1, 2]
    data = {"a": shared, "b": shared}
    filepath = tmp_path / "snapshot.json"

    json_recorder.save(data, filepath)

    assert json_recorder.load(filepath) == {"a": [1, 2], "b": [1, 2]}


class _IntSubclass(int):
    pass


class _FloatSubclass(float):
    pass


class _StrSubclass(str):
    pass


class _ListSubclass(list):
    pass


class _DictSubclass(dict):
    pass


@pytest.mark.parametrize(
    "data",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        (1, 2),
        {1, 2},
        frozenset({1, 2}),
        b"bytes",
        bytearray(b"bytes"),
        memoryview(b"bytes"),
        Decimal("1.2"),
        Fraction(1, 3),
        Path("snapshot.json"),
        object(),
        _IntSubclass(1),
        _FloatSubclass(1.0),
        _StrSubclass("x"),
        _ListSubclass(),
        _DictSubclass(),
    ],
)
def test_json_rejects_values_outside_strict_data_model(tmp_path: Path, data) -> None:
    filepath = tmp_path / "snapshot.json"

    with pytest.raises(DittoJSONSerializationError, match=r"at \$"):
        json_recorder.save(data, filepath)

    assert not filepath.exists()


@pytest.mark.parametrize(
    "data,path",
    [
        ({1: "value"}, r"\$\[<key>\]"),
        ({"outer": {1: "value"}}, r'\$\["outer"\]\[<key>\]'),
        ({"outer": [1, object()]}, r'\$\["outer"\]\[1\]'),
    ],
)
def test_json_error_reports_first_invalid_path(tmp_path: Path, data, path: str) -> None:
    with pytest.raises(DittoJSONSerializationError, match=path):
        json_recorder.save(data, tmp_path / "snapshot.json")


def test_json_rejects_list_cycle(tmp_path: Path) -> None:
    data: list[object] = []
    data.append(data)

    with pytest.raises(DittoJSONSerializationError, match=r"\$\[0\].*cyclic"):
        json_recorder.save(data, tmp_path / "snapshot.json")


def test_json_rejects_dict_cycle(tmp_path: Path) -> None:
    data: dict[str, object] = {}
    data["self"] = data

    with pytest.raises(DittoJSONSerializationError, match=r'\$\["self"\].*cyclic'):
        json_recorder.save(data, tmp_path / "snapshot.json")


class _Hostile:
    invoked: list[str] = []

    def _fail(self, protocol: str):
        self.invoked.append(protocol)
        raise AssertionError(f"{protocol} was invoked")

    def __iter__(self):
        return self._fail("__iter__")

    def __reduce__(self):
        return self._fail("__reduce__")

    def __reduce_ex__(self, protocol):
        return self._fail("__reduce_ex__")

    def __str__(self):
        return self._fail("__str__")

    def __bytes__(self):
        return self._fail("__bytes__")

    def __int__(self):
        return self._fail("__int__")

    def __float__(self):
        return self._fail("__float__")

    def __index__(self):
        return self._fail("__index__")


def test_json_does_not_invoke_hostile_protocols(tmp_path: Path) -> None:
    hostile = _Hostile()
    _Hostile.invoked.clear()

    with pytest.raises(DittoJSONSerializationError):
        json_recorder.save({"value": hostile}, tmp_path / "snapshot.json")

    assert _Hostile.invoked == []


def test_json_validation_does_not_replace_existing_file(tmp_path: Path) -> None:
    filepath = tmp_path / "snapshot.json"
    filepath.write_bytes(b"original")

    with pytest.raises(DittoJSONSerializationError):
        json_recorder.save((1, 2), filepath)

    assert filepath.read_bytes() == b"original"


@pytest.mark.parametrize("data", ["\ud800", {"\ud800": 1}])
def test_json_rejects_strings_that_cannot_be_encoded_as_utf8(
    tmp_path: Path, data
) -> None:
    with pytest.raises(DittoJSONSerializationError, match="valid UTF-8"):
        json_recorder.save(data, tmp_path / "snapshot.json")


def test_json_writes_deterministic_utf8_bytes(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    json_recorder.save(
        {"z": "snowman: ☃", "a": [1, 1.5, True, None, {"b": -0.0}]}, first
    )
    json_recorder.save(
        {"a": [1, 1.5, True, None, {"b": -0.0}], "z": "snowman: ☃"}, second
    )

    expected = (
        '{\n  "a": [\n    1,\n    1.5,\n    true,\n    null,\n'
        '    {\n      "b": -0.0\n    }\n  ],\n  "z": "snowman: ☃"\n}\n'
    ).encode()
    assert first.read_bytes() == expected
    assert second.read_bytes() == expected
    assert b"\r" not in expected


def test_json_repeated_writes_are_byte_identical(tmp_path: Path) -> None:
    filepath = tmp_path / "snapshot.json"
    data = {"nested": {"z": 3, "a": 1}, "unicode": "λ"}

    json_recorder.save(data, filepath)
    first = filepath.read_bytes()
    json_recorder.save(data, filepath)

    assert filepath.read_bytes() == first


def test_json_loads_compact_legacy_json(tmp_path: Path) -> None:
    filepath = tmp_path / "snapshot.json"
    filepath.write_bytes(b'{"b":[1,true],"a":null}')

    assert json_recorder.load(filepath) == {"b": [1, True], "a": None}
    assert filepath.read_bytes() == b'{"b":[1,true],"a":null}'


@pytest.mark.parametrize(
    "content,exc",
    [
        (b"{", _json.JSONDecodeError),
        (b'"\xff"', UnicodeDecodeError),
        (b'{"a": 1, "a": 2}', DittoJSONSerializationError),
        (b"NaN", DittoJSONSerializationError),
        (b"Infinity", DittoJSONSerializationError),
        (b"-Infinity", DittoJSONSerializationError),
        (b"1e400", DittoJSONSerializationError),
        (b"-1e400", DittoJSONSerializationError),
    ],
)
def test_json_rejects_invalid_or_non_strict_input(
    tmp_path: Path, content: bytes, exc: type[Exception]
) -> None:
    filepath = tmp_path / "snapshot.json"
    filepath.write_bytes(content)

    with pytest.raises(exc):
        json_recorder.load(filepath)


def test_json_accepts_numeric_underflow(tmp_path: Path) -> None:
    filepath = tmp_path / "snapshot.json"
    filepath.write_bytes(b"1e-400")

    value = json_recorder.load(filepath)

    assert value == 0.0
    assert type(value) is float


def test_json_decoder_constructs_only_plain_containers(tmp_path: Path) -> None:
    filepath = tmp_path / "snapshot.json"
    filepath.write_bytes(b'{"outer": [{"inner": 1}]}')

    value = json_recorder.load(filepath)

    assert type(value) is dict
    assert type(value["outer"]) is list
    assert type(value["outer"][0]) is dict


def test_yaml_roundtrip_preserves_supported_value(tmp_path: Path) -> None:
    filepath = tmp_path / "snapshot.yaml"
    data = {"key": [1, "two", 3.0]}

    yaml_recorder.save(data, filepath)

    assert yaml_recorder.load(filepath) == data


def test_yaml_raises_when_file_is_corrupt(tmp_path: Path) -> None:
    filepath = tmp_path / "corrupt.yaml"
    filepath.write_bytes(b"key: {unclosed")

    with pytest.raises(_yaml.YAMLError):
        yaml_recorder.load(filepath)
