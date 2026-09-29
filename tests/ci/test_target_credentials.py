"""Target URIs that carry secrets are refused, so ditto.lock never records them."""

import pytest

from ditto.plugin._options import reject_uri_credentials

pytest_plugins = ["pytester"]


@pytest.mark.parametrize(
    ("uri", "masked", "found"),
    [
        (
            "redis://alice:password@host:6379/0",
            "redis://alice:***@host:6379/0",
            "a password",
        ),
        ("redis://:pw@host/0", "redis://:***@host/0", "a password"),
        (
            "az://container/path?sv=2020&sig=abc&se=x",
            "az://container/path?sv=2020&sig=***&se=x",
            "the query parameter 'sig'",
        ),
        (
            "s3://bucket/key?X-Amz-Signature=abc",
            "s3://bucket/key?X-Amz-Signature=***",
            "the query parameter 'X-Amz-Signature'",
        ),
        (
            "postgresql://u:p@h/db?password=q",
            "postgresql://u:***@h/db?password=***",
            "a password and the query parameter 'password'",
        ),
    ],
    ids=["password", "password-only", "sas-sig", "presigned", "both"],
)
def test_uri_with_a_secret_is_rejected_with_it_masked(uri, masked, found) -> None:
    """The error shows the URI with every secret masked and says what it found."""
    with pytest.raises(pytest.UsageError) as excinfo:
        reject_uri_credentials(uri)

    message = str(excinfo.value)
    assert repr(masked) in message
    assert f"contains {found}." in message
    assert "ditto_storage_options" in message
    assert "password@" not in message and "=abc" not in message


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "file://.ditto",
        "memory://",
        "redis://localhost:6379/0",
        "redis://alice@host:6379/0",
        "s3://bucket/prefix/?region=eu-west-1",
    ],
    ids=["empty", "file", "memory", "plain", "username-only", "harmless-query"],
)
def test_uri_without_a_secret_is_accepted(uri) -> None:
    """A username alone, or a query parameter that isn't a secret, is allowed."""
    reject_uri_credentials(uri)


def test_mark_target_with_a_password_errors_and_is_not_locked(pytester) -> None:
    """A test whose mark target holds a password errors before any backend is
    built, and its URI never reaches ditto.lock."""
    pytester.makepyfile(
        test_m="""
        import ditto

        @ditto.record("json", target="memory://alice:hunter2@bucket/snaps")
        def test_t(snapshot):
            snapshot(1, key="k")
        """
    )

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(
        ["*memory://alice:***@bucket/snaps*contains a password*"]
    )
    lock = pytester.path / "ditto.lock"
    assert not lock.exists() or "hunter2" not in lock.read_text()


def test_ini_target_with_a_password_stops_the_run(pytester) -> None:
    """A `ditto_target` with a password is a usage error before any test runs."""
    pytester.makeini(
        """
        [pytest]
        ditto_target = redis://alice:hunter2@localhost:6379/0
        """
    )
    pytester.makepyfile(test_m="def test_t(snapshot):\n    snapshot(1, key='k')\n")

    result = pytester.runpytest_subprocess()

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*redis://alice:***@localhost:6379/0*"])
    assert "hunter2" not in result.stderr.str() + result.stdout.str()
