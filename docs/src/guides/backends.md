# Storage Backends

ditto stores each snapshot in a **target**: a location written as a URI, such
as a local directory, an S3 bucket or a Redis database. By default the target
is a `.ditto/` directory next to each test file. This guide explains how to
store snapshots somewhere else, for one test or for a whole project, and how to
pass the credentials that remote storage needs.

## Targets are URIs

A target URI has two parts. The **scheme**, before the first `:`, says what
kind of storage it is. The rest says where in that storage the snapshots go:

```
s3://my-bucket/snapshots/
^^   ^^^^^^^^^^^^^^^^^^^^
│    └ where: here, a bucket and a prefix within it
└ scheme
```

The scheme picks the **backend**, the code that reads and writes snapshots for
that kind of storage. ditto chooses the backend in this order:

1. `file` is always the local filesystem.
2. A scheme with a registered backend uses that backend. Packages register
   backends for storage such as Redis or PostgreSQL; see
   [Custom Backends](custom-backends.md) to write one.
3. Any [fsspec](https://filesystem-spec.readthedocs.io/) protocol, such as
   `s3`, `gs`, `az` or `memory`, uses fsspec.
4. Anything else fails the test with `ValueError: Unknown backend scheme`.

Common targets:

| Target | Stores snapshots in | Needs |
| --- | --- | --- |
| `file://.ditto` | a `.ditto/` directory next to each test file (the default) | nothing |
| `file://snapshots/api` | a `snapshots/api/` directory next to each test file | nothing |
| `file:///var/snapshots` | the absolute directory `/var/snapshots` | nothing |
| `memory://` | the memory of the current Python process | nothing |
| `s3://my-bucket/snapshots/` | the `snapshots/` prefix of an S3 bucket | [`s3fs`](https://s3fs.readthedocs.io/) |
| `gs://my-bucket/snapshots/` | the `snapshots/` prefix of a Google Cloud Storage bucket | [`gcsfs`](https://gcsfs.readthedocs.io/) |
| `az://my-container/snapshots/` | the `snapshots/` prefix of an Azure Blob Storage container | [`adlfs`](https://github.com/fsspec/adlfs) |
| `redis://localhost:6379/0` | database 0 of a Redis server | a package that registers a `redis` backend |

### Local files: `file://`

A `file://` target names a directory. Count the slashes:

- **Two slashes, a relative path.** `file://snapshots/api` is resolved against
  the directory of *each test file*, not the project root. Tests in
  `tests/api/` and `tests/cli/` store snapshots in `tests/api/snapshots/api/`
  and `tests/cli/snapshots/api/`.
- **Three slashes, an absolute path.** `file:///var/snapshots` is the same
  directory for every test.

The default, `file://.ditto`, is a relative path, which is why each test
directory gets its own `.ditto/`.

Each snapshot is one file, named after the test module, the test, the
snapshot key, a short hash and the recorder. The module path's slashes become
dots, so every file sits directly in the directory. For example, with the project root as pytest's
rootdir, a test `test_create` in `tests/api/test_users.py` that calls
`snapshot(value, key="response")` with the `json` recorder writes:

```
tests/api/.ditto/tests.api.test_users.test_create@response~90e755f5c20755bd.json
                 └────────┬─────────┘ └────┬────┘ └──┬───┘ └──────┬───────┘ └┬─┘
                     test module         test       key         hash     recorder
```

The module part is the test file's path relative to the rootdir, without its
extension.

The test and key are there to be read, not decoded, so they're made safe for
every file system: characters other than ASCII letters, digits and
`. _ - [ ] = , +` become `_`, and the test is shortened to 80 characters and the
key to 40. If the module path is long, they're shortened further so the whole
file name fits in 255 bytes; a module path too long to leave room for them is an
error.
The hash is the first 16 hex characters of a SHA-256 of the test's exact pytest
node ID, the key and the recorder. It keeps apart snapshots that would otherwise
share a name, such as parametrize IDs that differ only in case (`[A]` and `[a]`,
which are the same file name on Windows and macOS) or only in replaced
characters (`[12:00]` and `[12_00]`). `ditto.lock` records each snapshot's exact
test and key, and `ditto list` shows them.

A snapshot is written to a temporary file next to it, then renamed into place,
so a write that fails partway through (a full disk, an interrupted run) leaves
the previous snapshot intact. An overwritten snapshot keeps its permissions. A
process killed mid-write can leave the temporary file behind: `.ditto-tmp-`,
then 32 hex characters, then `.tmp`. ditto ignores it, and it's safe to delete.

### fsspec: cloud storage and memory

fsspec itself only understands a few protocols, such as `memory`. Most cloud
storage needs an extra package; the table above lists the common ones, and
[fsspec's list of implementations](https://filesystem-spec.readthedocs.io/en/latest/api.html#other-known-implementations)
has the rest. Without the package, tests that use the target fail with an
error that names it, such as `ImportError: Install s3fs to access S3`.

Snapshots are stored under the URI's path, one object per snapshot. The name
has the same parts as a local file's, but the module path keeps its slashes, and
the name isn't a file name, so it has no 255-byte limit: the test and key are
only shortened to 80 and 40 characters.
The same test as above, with `target="s3://my-bucket/snapshots/"`, writes:

```
s3://my-bucket/snapshots/tests/api/test_users/test_create@response~90e755f5c20755bd.json
                         └────────┬─────────┘ └────┬────┘ └──┬───┘ └──────┬───────┘ └┬─┘
                             test module         test       key         hash     recorder
```

`memory://` stores snapshots in the current Python process. A fresh process
starts empty, so it can't keep a baseline between ordinary command-line runs,
which makes it unsuitable for persistent regression snapshots.

## Choosing the target for a test

ditto uses the first of these that is set:

1. `target=` on the test's mark
2. `target_profile=` on the test's mark
3. The `ditto_target` ini option
4. The `ditto_target_profile` ini option
5. `file://.ditto`

A mark takes either `target=` or `target_profile=`, not both; a test with both
fails. Likewise, `ditto_target` and `ditto_target_profile` can't both be set,
and pytest refuses to start if they are. The profile options are described in
[Named profiles](#named-profiles).

### For one test: `target=`

```python
import ditto


@ditto.record("json", target="s3://my-bucket/snapshots/")
def test_create_user(snapshot): ...
```

### For a whole project: `ditto_target`

```toml
# pyproject.toml
[tool.pytest.ini_options]
ditto_target = "s3://my-bucket/snapshots/"
```

Every test without its own `target=` or `target_profile=` then uses this
target. A relative `file://` path here is still resolved against each test
file's directory.

!!! warning "Give each project and branch its own remote path"
    Snapshots are named after test modules, so two branches of a project, or
    two projects with the same test paths, sharing one target can't tell each
    other's snapshots from their own stale ones. Use a path per project and
    branch, such as `s3://my-bucket/<project>/<branch>/`. See
    [Sharing a target](lock-file.md#sharing-a-target).

## Credentials and connection settings: `ditto_storage_options`

Remote storage usually needs credentials or connection settings. They can't go
in target URIs: ditto writes every target URI to `ditto.lock`, which you
commit, so a password in a URI would end up in version control. ditto refuses a
target URI that contains a password (`redis://alice:secret@host`) or a query
parameter that holds a secret (`password`, `passwd`, `pwd`, `secret`,
`secret_key`, `token`, `access_token`, `api_key`, `apikey`, `sig`, `signature`,
`X-Amz-Signature` or `X-Amz-Security-Token`, in any case), including in any
part of a chained fsspec URL such as `simplecache::s3://…`. A test using one
errors, and a `ditto_target` with one stops the run. The error masks the secret
and is reported without a traceback, so the URI doesn't appear in pytest's
output (except under `--full-trace`). A username alone is fine. Return
credentials from a `ditto_storage_options` fixture in `conftest.py` instead, or
for a [profile](#named-profiles), from its own `storage_options`. The fixture
returns a dictionary keyed by scheme:

```python
# conftest.py
import os
import pytest


@pytest.fixture(scope="session")
def ditto_storage_options():
    return {
        "s3": {"key": os.environ["AWS_KEY"], "secret": os.environ["AWS_SECRET"]},
        "redis": {"password": os.environ["REDIS_PASSWORD"]},
    }
```

For each target, ditto looks up the entry for the target's scheme and passes
its items as keyword arguments to the backend. For an fsspec scheme, they go
to the fsspec filesystem, so the valid options are those of that filesystem,
such as s3fs's `key`, `secret` and `endpoint_url`. For a registered backend,
they go to the backend's factory; its documentation lists the options it
accepts.

- Options are chosen by scheme alone, so every `s3://` target gets the same
  options. To give two targets with the same scheme different credentials, use
  [profiles](#named-profiles).
- Options are never written to `ditto.lock`.
- Options may contain nested dictionaries, lists, tuples and sets. Values
  inside those containers must otherwise be hashable, because ditto uses the
  options to decide when two tests can share a backend; the backend still
  receives them unchanged. An unhashable value, such as a `bytearray`, fails
  with `DittoUnhashableStorageOptionsError`.

## Named profiles

A profile is a target with a name, and optionally its own storage options.
Profiles help when:

- several tests share one of a few targets, and the name says more than the URI
- two targets use the same scheme but need different credentials

### Defining profiles

A profile is either a URI, or a table with a `uri` and, optionally,
`storage_options`.

A profile's storage options replace `ditto_storage_options` entirely: a profile
target gets only the options in its own definition, even if
`ditto_storage_options` has an entry for its scheme, and a URI-only profile
gets none. The storage library can still find credentials the way it normally
does; s3fs, for example, reads the `AWS_*` environment variables and
`~/.aws/credentials`.

Define profiles in a `ditto_target_profiles` fixture when they need values from
the environment, such as secrets:

```python
# conftest.py
import os
import pytest


@pytest.fixture(scope="session")
def ditto_target_profiles():
    return {
        "golden": "s3://my-bucket/golden/",
        "s3_east": {
            "uri": "s3://east-bucket/golden/",
            "storage_options": {
                "key": os.environ["AWS_EAST_KEY"],
                "secret": os.environ["AWS_EAST_SECRET"],
            },
        },
    }
```

Or define them in `pyproject.toml` when they don't:

```toml
[tool.pytest-ditto.target_profiles]
golden = "s3://my-bucket/golden/"

[tool.pytest-ditto.target_profiles.s3_east]
uri = "s3://east-bucket/golden/"
storage_options = { endpoint_url = "https://s3.us-east-1.amazonaws.com" }
```

A name defined in both places is an error.

### Using profiles

For one test:

```python
import ditto


@ditto.record("json", target_profile="s3_east")
def test_create_user(snapshot): ...
```

For a whole project:

```toml
[tool.pytest.ini_options]
ditto_target_profile = "golden"
```

An unknown profile name fails the test, and the error lists the defined
profiles.

!!! note "Static profiles are only read from `pyproject.toml`"
    The `[tool.pytest-ditto.target_profiles]` table is read from the
    `pyproject.toml` in pytest's [rootdir](https://docs.pytest.org/en/stable/reference/customize.html#initialization-determining-rootdir-and-configfile),
    and nowhere else:

    - `pytest.ini`, `tox.ini` and `setup.cfg` cannot hold the table.
    - If pytest is configured by one of those files, a `pyproject.toml` next
      to it (in the rootdir) is still read.
    - A `pyproject.toml` in any other directory, such as a subdirectory of
      the rootdir, is ignored.

    Projects without a `pyproject.toml` in the rootdir can define the same
    profiles in the `ditto_target_profiles` fixture instead. Selecting a
    default profile with the `ditto_target_profile` ini option works from any
    pytest configuration file.
