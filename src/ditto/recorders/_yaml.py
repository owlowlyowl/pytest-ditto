import yaml as _yaml
from typing import Any

from ._protocol import Recorder


__all__ = ("yaml",)


def _dumps(data: Any) -> bytes:
    # SafeDumper escapes non-ASCII characters and always writes "\n", so the
    # bytes are the same on every platform.
    return _yaml.dump(data, Dumper=_yaml.SafeDumper).encode("utf-8")


def _loads(raw: bytes) -> Any:
    return _yaml.load(raw, Loader=_yaml.SafeLoader)


yaml = Recorder(dumps=_dumps, loads=_loads)
