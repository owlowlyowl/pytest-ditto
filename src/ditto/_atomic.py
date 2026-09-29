from __future__ import annotations

import os
import uuid
from pathlib import Path


__all__ = ("TEMP_PREFIX", "is_temp_name", "write_atomically")


# The start of every temporary file `write_atomically` creates. A process
# killed mid-write can leave one behind; `is_temp_name` recognises it.
TEMP_PREFIX = ".ditto-tmp-"


def is_temp_name(name: str) -> bool:
    """True when `name` is a file name `write_atomically` gave a temporary file."""
    return name.startswith(TEMP_PREFIX)


def write_atomically(path: Path, data: bytes) -> None:
    """Replace the contents of `path` with `data`, or leave `path` as it was.

    Writes `data` to a temporary file in the same directory, then
    `os.replace`s it over `path`, so a failure partway through (a full disk,
    an interrupted process) never leaves `path` half-written. The temporary
    file is removed when the write fails. Its name doesn't include `path`'s,
    so it stays within the file-name length limit, and it is created with the
    default permissions, as `open` would create `path`.
    """
    tmp = path.with_name(f"{TEMP_PREFIX}{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
