"""Filesystem boundary for the private result handoff."""

from pathlib import Path

from ._atomic import write_atomically
from ._results import OperationResult, decode_result, encode_result


def read_result(path: Path) -> OperationResult:
    """Read and validate one versioned result."""
    return decode_result(path.read_bytes())


def write_result(path: Path, result: OperationResult) -> None:
    """Publish a complete handoff atomically."""
    write_atomically(path, encode_result(result))
