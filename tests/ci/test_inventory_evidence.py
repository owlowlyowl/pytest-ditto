from __future__ import annotations

import pytest

from ditto._lockfile import LockEntry
from ditto._manifest import BackendManifest, ManifestEntry
from ditto._result_inventory import inventory_result
from ditto._credentials import mask_credentials
from ditto._results import Coverage, Identity


@pytest.mark.parametrize(
    "source,error,status",
    [
        ("live", None, "checked"),
        ("live", "secret", "failed"),
        ("lock", None, "unchecked"),
        ("unknown", None, "unchecked"),
    ],
)
def test_distinguishes_coverage_when_backend_inventory_is_empty(
    source: str,
    error: str | None,
    status: str,
) -> None:
    """Empty inventory does not conceal failed or unexamined coverage."""
    manifest = [BackendManifest("target", [], error)]

    result = inventory_result(manifest, "tests/", {"target": source}, {})
    actual = result.coverage[0].status

    expected = status
    assert actual == expected


def test_retains_exact_owner_when_inventory_comes_from_lock() -> None:
    """Lock-backed inventory retains the exact recorded snapshot identity."""
    owner = LockEntry("test_x.py::test_t[12:00]", "raw:value", "json")
    manifest = [BackendManifest("remote", [ManifestEntry("hashed", None, None)])]

    result = inventory_result(
        manifest,
        "tests/",
        {"remote": "lock"},
        {("remote", "hashed"): owner},
    )
    actual = result.items[0].object.identity

    expected = Identity(owner.nodeid, owner.key, owner.recorder)
    assert actual == expected


def test_keeps_presence_unknown_when_inventory_comes_from_lock() -> None:
    """A lock entry does not prove the stored object exists."""
    manifest = [BackendManifest("remote", [ManifestEntry("hashed", None, None)])]

    result = inventory_result(manifest, "tests/", {"remote": "lock"}, {})
    actual = result.items[0].presence

    expected = "unknown"
    assert actual == expected


def test_keeps_owner_unknown_when_only_storage_label_is_available() -> None:
    """Hashed storage labels cannot establish snapshot ownership."""
    manifest = [BackendManifest("disk", [ManifestEntry("unknown-hash", 12, None)])]

    result = inventory_result(manifest, "tests/", {"disk": "disk"}, {})

    assert result.items[0].object.identity is None


def test_preserves_physical_metadata_when_backend_reports_it() -> None:
    """Physical metadata retains byte units and POSIX timestamps."""
    manifest = [BackendManifest("disk", [ManifestEntry("hashed", 12, 123.5)])]

    result = inventory_result(manifest, "tests/", {"disk": "disk"}, {})
    metadata = result.items[0].metadata
    actual = (metadata.size_bytes, metadata.source)

    expected = (12, "disk")
    assert actual == expected
    assert metadata.modified == pytest.approx(123.5)


def test_omits_backend_secrets_when_inventory_enumeration_fails() -> None:
    """Backend diagnostics never copy exception secrets into result evidence."""
    manifest = [BackendManifest("failed", [], "password=supersecret")]

    result = inventory_result(manifest, "tests/", {"failed": "live"}, {})
    actual = result.coverage

    expected = (
        Coverage(
            "failed",
            "live",
            "failed",
            "Backend inventory failed; details remain in the source diagnostic",
        ),
    )
    assert actual == expected


@pytest.mark.parametrize(
    "location,expected",
    [
        (
            "s3://user:secret@bucket/path?token=secret",
            "s3://user:***@bucket/path?token=***",
        ),
        (
            "simplecache::s3://user:secret@bucket/path?sig=secret",
            "simplecache::s3://user:***@bucket/path?sig=***",
        ),
        (
            "s3://bucket/path?X-Amz-Signature=secret",
            "s3://bucket/path?X-Amz-Signature=***",
        ),
    ],
)
def test_redacts_secrets_when_target_has_uri_credentials(
    location: str,
    expected: str,
) -> None:
    """Target locations omit URI passwords and signed query values."""
    actual = mask_credentials(location)

    assert actual == expected


@pytest.mark.parametrize(
    "location", ["redis://host/0?namespace=a", "redis://host/0?keyspace=b"]
)
def test_preserves_target_identity_when_uri_options_are_public(location: str) -> None:
    """Public URI options, even ones named like secrets, still distinguish targets."""
    actual = mask_credentials(location)

    expected = location
    assert actual == expected
