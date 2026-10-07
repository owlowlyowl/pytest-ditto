"""Rules for the GitHub Actions workflows under .github/workflows/."""

from pathlib import Path

import pytest
import yaml


WORKFLOWS = Path(__file__).parents[2] / ".github" / "workflows"


def test_requires_every_other_ci_job_when_integration_is_advisory() -> None:
    """The required CI gate includes every job except advisory integration."""
    # `CI` is the one CI check the main ruleset requires, so a job missing from its
    # `needs` could fail without blocking a merge. Integration is advisory on
    # PRs because it depends on Docker image pulls; it gates releases instead.
    jobs = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())["jobs"]

    actual = set(jobs["ci"]["needs"])
    expected = set(jobs) - {"ci", "integration"}
    assert actual == expected
    assert "integration" in jobs


@pytest.mark.parametrize("filename", ["release.yml", "pre-release-test.yml"])
def test_requires_integration_when_release_testing_runs(filename: str) -> None:
    """Both release workflows require the full integration suite to succeed."""
    jobs = yaml.safe_load((WORKFLOWS / filename).read_text())["jobs"]

    actual = jobs["test"]["strategy"]["matrix"]["include"]
    expected = {"environment": "integration", "task": "test-integration"}
    assert expected in actual
    assert not jobs["test"].get("continue-on-error", False)


def test_requires_successful_tests_when_publishing() -> None:
    """Publishing waits for every release test environment to succeed."""
    jobs = yaml.safe_load((WORKFLOWS / "release.yml").read_text())["jobs"]

    actual = jobs["publish"]["needs"]
    assert "test" in actual
