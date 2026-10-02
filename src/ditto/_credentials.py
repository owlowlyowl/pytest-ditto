from __future__ import annotations

from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse


__all__ = ("mask_credentials", "uri_credentials_error")


# Query parameters whose values are secrets, compared case-insensitively: a
# password, a token or key, or a signed URL's signature (Azure SAS `sig`,
# S3 presigned `X-Amz-Signature` and `X-Amz-Security-Token`).
_SECRET_QUERY_PARAMS = frozenset({
    "password",
    "passwd",
    "pwd",
    "secret",
    "secret_key",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "sig",
    "signature",
    "x-amz-signature",
    "x-amz-security-token",
})


def _is_secret_param(name: str) -> bool:
    """True when a query parameter called `name` holds a secret."""
    return name.lower() in _SECRET_QUERY_PARAMS


def _secret_param_names(parsed: ParseResult) -> list[str]:
    """Return the names of `parsed`'s query parameters that hold secrets."""
    query = parse_qsl(parsed.query, keep_blank_values=True)
    return [name for name, _ in query if _is_secret_param(name)]


def _masked(part: str) -> str:
    """Return `part` with its password and secret query values replaced by `***`.

    `part` is returned unchanged when it holds no secret.
    """
    parsed = urlparse(part)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    has_password = parsed.password is not None
    if not has_password and not any(_is_secret_param(name) for name, _ in query):
        return part
    netloc = parsed.netloc
    if has_password:
        userinfo, _, hostport = netloc.rpartition("@")
        netloc = f"{userinfo.partition(':')[0]}:***@{hostport}"
    masked_query = urlencode(
        [(n, "***" if _is_secret_param(n) else v) for n, v in query], safe="*"
    )
    return parsed._replace(netloc=netloc, query=masked_query).geturl()


def mask_credentials(uri: str) -> str:
    """Return `uri` with each part's password and secret query values masked.

    Each part of an fsspec chain (`simplecache::s3://...`) is masked. A URI
    that can't be parsed is replaced whole, since it can't be masked safely.
    """
    try:
        return "::".join(_masked(part) for part in uri.split("::"))
    except ValueError:
        return "<invalid target URI>"


def uri_credentials_error(uri: str) -> str | None:
    """Return why a target URI can't be used because it carries a secret, or None.

    A target URI other than `file://` is recorded verbatim in `ditto.lock`,
    which is committed, so a password in its userinfo (`redis://u:pw@host`) or
    a secret query parameter (`?sig=...`) would be committed with it. Each
    part of an fsspec chain (`simplecache::s3://...`) is checked. The message
    shows the URI with the secrets masked. A username alone isn't a secret
    and is allowed.
    """
    parts = uri.split("::") if uri else []
    parsed_parts = [urlparse(part) for part in parts]
    has_password = any(parsed.password is not None for parsed in parsed_parts)
    param_names = [
        name for parsed in parsed_parts for name in _secret_param_names(parsed)
    ]
    if not has_password and not param_names:
        return None
    found = (["a password"] if has_password else []) + [
        f"the query parameter {name!r}" for name in param_names
    ]
    masked = "::".join(_masked(part) for part in parts)
    return (
        f"ditto target {masked!r} contains {' and '.join(found)}. Target URIs "
        "are recorded in ditto.lock, which is committed. Pass credentials "
        "through the ditto_storage_options fixture, or a profile's "
        "storage_options, instead."
    )
