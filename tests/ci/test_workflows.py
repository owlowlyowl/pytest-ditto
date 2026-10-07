"""Rules for the GitHub Actions workflows under .github/workflows/."""

from pathlib import Path

import yaml


WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"


def test_ci_gate_needs_every_required_ci_job() -> None:
    # `CI` is the one CI check the main ruleset requires, so a job missing from its
    # `needs` could fail without blocking a merge. Integration is advisory on
    # PRs because it depends on Docker image pulls; it gates releases instead.
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]

    assert set(jobs["ci"]["needs"]) == set(jobs) - {"ci", "integration"}


def test_integration_gates_release_and_pre_release_testing() -> None:
    for filename in ("release.yml", "pre-release-test.yml"):
        jobs = yaml.safe_load((WORKFLOWS / filename).read_text())["jobs"]
        assert {"environment": "integration", "task": "test-integration"} in (
            jobs["test"]["strategy"]["matrix"]["include"]
        )
        assert not jobs["test"].get("continue-on-error", False)
        if "publish" in jobs:
            assert "test" in jobs["publish"]["needs"]
