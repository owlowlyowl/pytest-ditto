"""The version of pytest-ditto and every plugin, from ``git describe``.

A tagged commit gets the tag: ``2.0.0``, ``2.0.0rc1``. The Nth commit after the latest
tag gets ``<tag>.post0.dev<N>+<sha>``, which sorts after the tag and before the next
one. Plugins read this file too (``../../version_builder.py``), so every package in
the repository shares one version.

Needs full history and tags: in a shallow clone ``git describe`` can't count the
commits since the tag, so the version would be wrong. In CI, check out with
``fetch-depth: 0``.
"""

import subprocess


def _git(*args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{process.stdout}")
    return process.stdout.strip()


def _version() -> str:
    if _git("rev-parse", "--is-shallow-repository") == "true":
        raise RuntimeError(
            "Can't compute the version from a shallow clone. Fetch the full history "
            "and tags (`git fetch --unshallow --tags`), or in GitHub Actions check "
            "out with `fetch-depth: 0`."
        )

    tag, commits_since_tag, sha = _git("describe", "--tags", "--long").rsplit("-", 2)
    if commits_since_tag == "0":
        return tag
    # `describe` prefixes the abbreviated SHA with "g".
    return f"{tag}.post0.dev{commits_since_tag}+{sha.removeprefix('g')}"


if __name__ == "__main__":
    print(_version())
