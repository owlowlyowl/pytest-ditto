"""Behavioural tests for the introspection manifest schema."""

from ditto._manifest import (
    BackendManifest,
    ManifestEntry,
    from_json,
    to_json,
)


def test_round_trips_a_populated_manifest_through_json() -> None:
    """Backends and entries survive JSON serialization unchanged."""
    manifest = [
        BackendManifest(
            location="redis://localhost:6379/0",
            entries=[ManifestEntry("m/test_foo@v.pkl", size_bytes=128, modified=None)],
        )
    ]

    actual = from_json(to_json(manifest))

    assert actual == manifest


def test_round_trips_an_empty_manifest_through_json() -> None:
    """An empty backend list serializes and deserializes to an equal value."""
    manifest: list[BackendManifest] = []

    actual = from_json(to_json(manifest))

    assert actual == manifest
