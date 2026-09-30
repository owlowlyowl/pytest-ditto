"""Plugin health checks and snapshot metadata linting."""

from __future__ import annotations

import importlib.metadata
import importlib.util
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ditto._manifest import ManifestEntry
from ditto.exceptions import DittoBackendConflictError, DittoRecorderConflictError
from ditto.recorders._plugins import RecorderRegistry
from ._data import RecorderInfo, _parse_snapshot_name

if TYPE_CHECKING:
    from ditto.backends import BackendRegistry

_PLUGIN_MODULE = "ditto.plugin"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class LintIssue:
    filename: str
    issue: str
    location: str = ""


def _plugin_check() -> CheckResult:
    """Check that pytest will load the ditto plugin.

    The plugin is identified by the module its `pytest11` entry point targets,
    not by the entry-point name. pytest registers only the first plugin under a
    given name and silently skips the rest, so another plugin claiming the same
    name is reported as a failure.
    """
    name = "ditto plugin registered"
    pytest11 = list(importlib.metadata.entry_points(group="pytest11"))

    ours = next((ep for ep in pytest11 if ep.value == _PLUGIN_MODULE), None)
    if ours is None:
        return CheckResult(
            name=name,
            ok=False,
            detail=f"no pytest11 entry point targets {_PLUGIN_MODULE!r}",
        )

    clashes = sorted(
        {ep.value for ep in pytest11 if ep.name == ours.name} - {_PLUGIN_MODULE}
    )
    if clashes:
        return CheckResult(
            name=name,
            ok=False,
            detail=(
                f"pytest11 name {ours.name!r} is also claimed by "
                f"{', '.join(clashes)}; pytest loads only one of them"
            ),
        )

    try:
        ours.load()
    except Exception as exc:
        return CheckResult(name=name, ok=False, detail=str(exc))
    return CheckResult(name=name, ok=True, detail="")


def _doctor_checks() -> list[CheckResult]:
    """Return health-check results.

    Reads installed package metadata and imports the registered plugins to check
    they load; does not write to disk or render output.
    """
    results: list[CheckResult] = []

    results.append(
        CheckResult(
            name="pytest importable",
            ok=importlib.util.find_spec("pytest") is not None,
            detail="",
        )
    )

    results.append(_plugin_check())
    results.extend(_recorder_checks(RecorderRegistry()))
    # Imported here: `ditto.backends` imports fsspec, which other commands skip.
    from ditto.backends import BackendRegistry

    results.extend(_backend_checks(BackendRegistry()))
    return results


def _recorder_checks(registry: RecorderRegistry) -> list[CheckResult]:
    """Check each recorder loads and the registrations keep the plugin contract.

    A contract problem gets one failing row; the recorders it affects are not
    listed again.
    """
    results = [
        CheckResult(name="plugin contract", ok=False, detail=problem.message)
        for problem in registry.problems
    ]
    for name in registry:
        try:
            registry[name]
        except DittoRecorderConflictError:
            continue
        except Exception as exc:
            results.append(
                CheckResult(name=f"recorder: {name}", ok=False, detail=str(exc))
            )
        else:
            results.append(CheckResult(name=f"recorder: {name}", ok=True, detail=""))
    return results


def _backend_checks(registry: BackendRegistry) -> list[CheckResult]:
    """Check each backend loads and the registrations keep the plugin contract.

    A contract problem gets one failing row; the schemes it affects are not
    listed again.
    """
    results = [
        CheckResult(name="backend contract", ok=False, detail=problem.message)
        for problem in registry.problems
    ]
    for scheme in registry:
        try:
            registry[scheme]
        except DittoBackendConflictError:
            continue
        except Exception as exc:
            results.append(
                CheckResult(name=f"backend: {scheme}", ok=False, detail=str(exc))
            )
        else:
            results.append(CheckResult(name=f"backend: {scheme}", ok=True, detail=""))
    return results


def _find_lint_issues(
    entries: list[ManifestEntry], em: Mapping[str, RecorderInfo], *, location: str = ""
) -> list[LintIssue]:
    """Return lint issues for inventory entries without further I/O."""
    issues: list[LintIssue] = []
    for entry in entries:
        _, _, ext = _parse_snapshot_name(entry.storage_key)
        if ext == "":
            issues.append(
                LintIssue(
                    filename=entry.storage_key,
                    location=location,
                    issue="Malformed name (expected <test>@<key>~<hash>.<recorder>)",
                )
            )
        elif ext not in em:
            issues.append(
                LintIssue(
                    filename=entry.storage_key,
                    location=location,
                    issue=f"Unknown recorder identifier: {ext!r}",
                )
            )
        if entry.size_bytes == 0:
            issues.append(
                LintIssue(
                    filename=entry.storage_key, location=location, issue="Empty file"
                )
            )
    return issues
