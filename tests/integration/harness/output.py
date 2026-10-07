from __future__ import annotations


def table_rows(output: str) -> list[tuple[str, ...]]:
    """Read cell values independently of Rich's borders and column padding."""
    return [
        tuple(cell.strip() for cell in line.split("│")[1:-1])
        for line in output.splitlines()
        if line.startswith("│")
    ]


def panel_lines(output: str) -> list[str]:
    """Read panel text with layout whitespace normalized."""
    return [
        " ".join(line.strip("│ ").split())
        for line in output.splitlines()
        if line.startswith("│")
    ]
