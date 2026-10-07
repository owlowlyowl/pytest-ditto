"""Rules for the GitHub Actions workflows under .github/workflows/."""

from pathlib import Path

import yaml


WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"


def test_ci_gate_needs_every_other_ci_job() -> None:
    # `CI` is the one CI check the main ruleset requires, so a job missing from its
    # `needs` could fail without blocking a merge.
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]

    assert set(jobs["ci"]["needs"]) == set(jobs) - {"ci"}
