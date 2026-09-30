from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path


__all__ = ("TEMP_PREFIX", "is_temp_name", "write_atomically")


# The start of every temporary file `write_atomically` creates.
TEMP_PREFIX = ".ditto-tmp-"
# The exact name `write_atomically` gives a temporary file. ditto reserves it:
# a process killed mid-write can leave one behind, and `is_temp_name`
# recognises it.
_TEMP_NAME = re.compile(rf"{re.escape(TEMP_PREFIX)}[0-9a-f]{{32}}\.tmp")


def is_temp_name(name: str) -> bool:
    """True when `name` is a file name `write_atomically` gave a temporary file."""
    return _TEMP_NAME.fullmatch(name) is not None


def write_atomically(path: Path, data: bytes) -> None:
    """Replace the contents of `path` with `data`, or leave `path` as it was.

    Writes `data` to a temporary file in the same directory, then
    `os.replace`s it over `path`, so a failure partway through (a full disk,
    an interrupted process) never leaves `path` half-written. The temporary
    file is removed when the write fails. Its name doesn't include `path`'s,
    so it stays within the file-name length limit. Used for both snapshots
    and `ditto.lock`.

    The replacement is a new file. When `path` already exists, it gets
    `path`'s permission bits; otherwise the default ones, as `open` would give
    it. Ownership, ACLs and a symlink at `path` aren't preserved.

    Notes
    -----
    fsspec has its own helper for this, `fsspec.utils.atomic_write`, but it
    doesn't fit here:

    - Its temporary file's name starts with `path`'s. Snapshot names can use
      the whole 255-byte limit, so the temporary name would be too long.
    - It creates the file with `mkstemp`, so the result is always 0600.
    - If the final `os.replace` fails, the temporary file is left behind.

    fsspec's `open(..., autocommit=False)` and `fs.transaction` don't fit
    either. They put the temporary file in the system temp directory and
    commit with `shutil.move`, which copies into the destination (emptying it
    first) when the two are on different filesystems. They also change the
    shared, cached filesystem instance.
    """
    tmp = path.with_name(f"{TEMP_PREFIX}{uuid.uuid4().hex}.tmp")
    f = tmp.open("xb")  # if this fails, there's no file of ours to remove
    try:
        with f:
            f.write(data)
        try:
            shutil.copymode(path, tmp)
        except FileNotFoundError:
            pass
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
