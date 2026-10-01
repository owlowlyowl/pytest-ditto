"""CLI rendering treats user-derived names and errors as literal text."""

from io import StringIO

from click.testing import CliRunner
from rich.console import Console

from ditto._inventory import InventoryError
from ditto._manifest import BackendManifest, ManifestEntry
from ditto.cli import _inventory as cli_inventory
from ditto.cli import cli
from ditto.cli._data import RecorderInfo
from ditto.cli._diagnostics import CheckResult, LintIssue
from ditto.cli._display import (
    _render_doctor,
    _render_lint_issues,
    _render_recorders,
    _render_snapshots,
    _render_stats_table,
)
from ditto.cli._summary import gather_stats


def render(renderer, *args, width=80, **kwargs):
    stream = StringIO()
    console = Console(file=stream, width=width, color_system=None)
    renderer(*args, console, **kwargs)
    return stream.getvalue()


def test_lint_keeps_parametrize_ids_and_closing_tags():
    output = render(
        _render_lint_issues,
        [
            LintIssue(
                "tests.test_x.test_c[a]@k~0123456789abcdef.json",
                "Malformed name (expected <test>@<key>~<hash>.<recorder>)",
            ),
            LintIssue("[/x]file", "[/]error[red]"),
        ],
        width=120,
    )
    assert "tests.test_x.test_c[a]@k~0123456789abcdef.json" in output
    assert "[/x]file" in output
    assert "[/]error[red]" in output


def test_doctor_keeps_bracketed_detail():
    output = render(
        _render_doctor,
        [CheckResult("[bold]check[/]", False, "[/]error[red]")],
        width=120,
    )
    assert "[bold]check[/]" in output
    assert "[/]error[red]" in output


def test_recorders_keep_bracketed_plugin_metadata():
    output = render(
        _render_recorders,
        [RecorderInfo("[red]", "[/]", "[bold]package[/]")],
        width=120,
    )
    assert "[red]" in output
    assert "[/]" in output
    assert "[bold]package[/]" in output


def test_stats_table_keeps_bracketed_locations():
    output = render(
        _render_stats_table,
        [("memory://[red]", gather_stats([], {}))],
        width=120,
    )
    assert "memory://[red]" in output


def test_list_keeps_parametrize_ids_in_unlocked_names():
    stored = "tests.test_x.test_c[a]@k~0123456789abcdef.json"
    output = render(
        _render_snapshots,
        [BackendManifest("memory://one", [ManifestEntry(stored, 1, None)])],
        None,
        [],
        width=120,
    )
    assert "tests.test_x.test_c[a]" in output


def test_inventory_error_with_markup_is_literal(tmp_path, monkeypatch):
    def fail_inventory(path, *, live):
        raise InventoryError("bad [/][red] path")

    monkeypatch.setattr(cli_inventory, "build_inventory", fail_inventory)
    result = CliRunner().invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 1
    assert "bad [/][red] path" in result.output
    assert "Inventory failed" in result.output
