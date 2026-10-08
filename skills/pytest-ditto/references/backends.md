# Backends, credentials, and shared storage

Read this reference when choosing or inspecting targets, using profiles,
diagnosing unavailable storage, or changing remote baselines.

## Resolve the target

The first configured choice wins:

1. `target=` on the test's `@ditto.record(...)` mark.
2. `target_profile=` on that mark.
3. The `ditto_target` pytest ini option.
4. The `ditto_target_profile` pytest ini option.
5. `file://.ditto`, the local default.

A mark cannot specify both target and profile, and the two ini defaults cannot
both be set. Inspect relevant marks, configuration, and `conftest.py` fixtures
before running tests that could write to their targets.

`file://snapshots/api` is relative to each test file's directory, not the project
root. `file:///absolute/path` is absolute. `memory://` is process-local and loses
baselines between separate command-line runs; it is unsuitable for persistent
regression baselines.

The `file` scheme uses local storage. Other schemes use a registered backend
first, then fsspec when it supports the scheme. Some require extra packages,
such as `s3fs` for S3. Diagnose a missing implementation rather than silently
replacing the target.

## Credentials and profiles

Use `ditto_storage_options`, a fixture mapping schemes to connection options,
or a named profile's `storage_options`. Obtain secrets through the project's
existing credential mechanism. Target URIs are stored in the committed lock;
ditto rejects passwords and secret query parameters in URIs.

Profiles can be defined by a `ditto_target_profiles` fixture or in
`[tool.pytest-ditto.target_profiles]` in the rootdir's `pyproject.toml`. A profile
can be a URI or a table with `uri` and `storage_options`. Its storage options
replace the scheme-based fixture's options, rather than merging with them;
a URI-only profile supplies none. The storage library can still discover
credentials through its usual environment or configuration.

If credentials or the service are unavailable, inspect configuration and the
lock, run credential-free inventory where useful, and report that live checks
remain unverified. Keep the selected backend and the baseline policy intact.

## Declared versus live inventory

`ditto list`, `status`, `stats`, and `lint` do not import test modules by default:

- Local targets are inspected on disk, including on-disk orphans.
- Remote targets are read from `ditto.lock`; physical size and modification time
  are unknown, and drift cannot be inferred from that declared inventory.

`--live` runs a pytest setup-only introspection pass, imports test modules, and
needs the same connections and credentials as those fixtures. It reads physical
storage across the resolved targets. `ditto verify` runs test bodies and checks
only exercised targets against the lock. Neither a default inventory nor a
verify run exercising no snapshot targets proves that remote storage matches.

## Shared storage

Every checkout using the same target reads and writes the same snapshot keys.
Updating a remote baseline on one branch therefore changes what another branch
compares against. Module-prefix ownership separates suites with different test
paths, but it cannot distinguish branches or projects using the same paths.

For an authorized remote update, establish that the project's shared baseline
workflow permits that change. Do not change target paths as an incidental fix:
remote URIs are lock identities, and a new branch-specific path does not inherit
the old path's lock entries.

Prune guards any remote target and any `file://` directory outside the project,
after resolving symlinks. Without `--shared`, it leaves such orphans untouched
and fails. `ditto prune --check` lists them separately. Use `--shared` only when
the cleanup is authorized and the target is dedicated to this suite's baseline
workflow, so another branch or project is not depending on those keys. If
ownership is unknown, retain the candidates and report the unresolved scope.

Further details: [storage backends](https://owlowlyowl.github.io/pytest-ditto/guides/backends/)
and [sharing a target](https://owlowlyowl.github.io/pytest-ditto/concepts/lock-file/#sharing-a-target).
