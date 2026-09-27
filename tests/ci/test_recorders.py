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
def test_recorder_serialises_to_bytes(recorder) -> None:
    actual = recorder.dumps(1)

    assert isinstance(actual, bytes)


@pytest.mark.parametrize("recorder", [json_recorder, yaml_recorder])
def test_text_recorder_writes_newlines_without_carriage_returns(recorder) -> None:
    """Text snapshots are byte-identical on every platform."""
    actual = recorder.dumps({"a": [1, 2], "b": {"c": "d"}})

    assert b"\n" in actual
    assert b"\r" not in actual


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
def test_json_roundtrip_accepts_strict_data_model(data) -> None:
    actual = json_recorder.loads(json_recorder.dumps(data))

    assert actual == data


def test_json_accepts_shared_acyclic_containers() -> None:
    shared = [1, 2]
    data = {"a": shared, "b": shared}

    actual = json_recorder.loads(json_recorder.dumps(data))

    assert actual == {"a": [1, 2], "b": [1, 2]}


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
def test_json_rejects_values_outside_strict_data_model(data) -> None:
    with pytest.raises(DittoJSONSerializationError, match=r"at \$"):
        json_recorder.dumps(data)


@pytest.mark.parametrize(
    "data,path",
    [
        ({1: "value"}, r"\$\[<key>\]"),
        ({"outer": {1: "value"}}, r'\$\["outer"\]\[<key>\]'),
        ({"outer": [1, object()]}, r'\$\["outer"\]\[1\]'),
    ],
)
def test_json_error_reports_first_invalid_path(data, path: str) -> None:
    with pytest.raises(DittoJSONSerializationError, match=path):
        json_recorder.dumps(data)


def test_json_rejects_list_cycle() -> None:
    data: list[object] = []
    data.append(data)

    with pytest.raises(DittoJSONSerializationError, match=r"\$\[0\].*cyclic"):
        json_recorder.dumps(data)


def test_json_rejects_dict_cycle() -> None:
    data: dict[str, object] = {}
    data["self"] = data

    with pytest.raises(DittoJSONSerializationError, match=r'\$\["self"\].*cyclic'):
        json_recorder.dumps(data)


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


def test_json_does_not_invoke_hostile_protocols() -> None:
    hostile = _Hostile()
    _Hostile.invoked.clear()

    with pytest.raises(DittoJSONSerializationError):
        json_recorder.dumps({"value": hostile})

    assert _Hostile.invoked == []


@pytest.mark.parametrize("data", ["\ud800", {"\ud800": 1}])
def test_json_rejects_strings_that_cannot_be_encoded_as_utf8(data) -> None:
    with pytest.raises(DittoJSONSerializationError, match="valid UTF-8"):
        json_recorder.dumps(data)


def test_json_writes_deterministic_utf8_bytes() -> None:
    first = json_recorder.dumps({
        "z": "snowman: ☃",
        "a": [1, 1.5, True, None, {"b": -0.0}],
    })
    second = json_recorder.dumps({
        "a": [1, 1.5, True, None, {"b": -0.0}],
        "z": "snowman: ☃",
    })

    expected = (
        '{\n  "a": [\n    1,\n    1.5,\n    true,\n    null,\n'
        '    {\n      "b": -0.0\n    }\n  ],\n  "z": "snowman: ☃"\n}\n'
    ).encode()
    assert first == expected
    assert second == expected


def test_json_repeated_writes_are_byte_identical() -> None:
    data = {"nested": {"z": 3, "a": 1}, "unicode": "λ"}

    first = json_recorder.dumps(data)

    assert json_recorder.dumps(data) == first


def test_json_loads_compact_legacy_json() -> None:
    actual = json_recorder.loads(b'{"b":[1,true],"a":null}')

    assert actual == {"b": [1, True], "a": None}


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
    content: bytes, exc: type[Exception]
) -> None:
    with pytest.raises(exc):
        json_recorder.loads(content)


def test_json_accepts_numeric_underflow() -> None:
    value = json_recorder.loads(b"1e-400")

    assert value == 0.0
    assert type(value) is float


def test_json_decoder_constructs_only_plain_containers() -> None:
    value = json_recorder.loads(b'{"outer": [{"inner": 1}]}')

    assert type(value) is dict
    assert type(value["outer"]) is list
    assert type(value["outer"][0]) is dict


def test_yaml_roundtrip_preserves_supported_value() -> None:
    data = {"key": [1, "two", 3.0]}

    actual = yaml_recorder.loads(yaml_recorder.dumps(data))

    assert actual == data


def test_yaml_writes_ascii_with_newlines() -> None:
    """Non-ASCII is escaped and lines end in "\\n", so bytes match everywhere."""
    actual = yaml_recorder.dumps({"b": [1, "two"], "a": "caf\u00e9"})

    expected = b'a: "caf\\xE9"\nb:\n- 1\n- two\n'
    assert actual == expected


def test_yaml_raises_when_content_is_corrupt() -> None:
    with pytest.raises(_yaml.YAMLError):
        yaml_recorder.loads(b"key: {unclosed")


# ── Committed snapshots ───────────────────────────────────────────────────────

SNAPSHOTS = Path(__file__).parent / ".ditto"


def _recorder_name(path: Path) -> str:
    """The recorder name that ends a snapshot filename, e.g. `yaml`."""
    return path.name.rpartition("@")[2].partition(".")[2]


@pytest.mark.parametrize(
    "path",
    [p for p in sorted(SNAPSHOTS.iterdir()) if _recorder_name(p) in {"json", "yaml"}],
    ids=lambda p: p.name,
)
def test_rewriting_a_committed_text_snapshot_reproduces_its_bytes(path: Path) -> None:
    """Loading a committed snapshot and dumping it again gives the same bytes."""
    recorder = recorders.get(_recorder_name(path))
    raw = path.read_bytes()

    actual = recorder.dumps(recorder.loads(raw))

    assert actual == raw
