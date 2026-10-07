# Security Policy

## Snapshot formats

pytest-ditto core uses strict standard-library JSON by default. Core JSON
decoding constructs only plain JSON values, rejects duplicate object keys and
non-finite numbers, and does not expose user-selectable object construction
hooks.

Recorder and backend plugins are trusted Python packages: installing or loading
one executes that package's code independently of snapshot parsing. Review the
source and provenance of external plugins before use.

Pickle is not implemented or selected by pytest-ditto core. The external
`pytest-ditto-pickle` package is available for deliberate use, but loading
pickle data can execute arbitrary code. Never load pickle snapshots from an
untrusted source.

## Reporting a vulnerability

Please use GitHub's private vulnerability-reporting workflow for the
pytest-ditto repository. Do not include secrets or malicious payloads in a
public issue.
