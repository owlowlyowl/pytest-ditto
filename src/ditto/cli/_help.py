"""Help text shared by the CLI commands."""

from __future__ import annotations


__all__ = ("examples",)


def examples(*commands: str) -> str:
    """Return a command's help epilog listing `commands` as examples.

    Examples live in the epilog rather than the docstring because the CLI
    reference renders each docstring as Markdown, which would run the lines
    together. `\\b` stops click rewrapping them in `--help`.
    """
    return "\b\nExamples:\n" + "\n".join(f"  {command}" for command in commands)
