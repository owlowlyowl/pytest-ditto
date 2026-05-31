# Documentation alignment review

Reviewed against `main` at `91a265a` in the worktree `/home/oats/workspace/pytest-ditto-main-review`.

## Method

- Reviewed all 28 pages under `docs/src/`.
- Compared each page to the current implementation in `src/ditto/`, `pyproject.toml`, relevant examples, and the matching tests in `tests/ci/`.
- Built the docs and ran the existing test suite for the reviewed `main` snapshot:
  - `pixi run -e py312 test -q`
  - `pixi run -e docs docs-build`

## Executive summary

| Verdict | Count | Notes |
|---|---:|---|
| Aligned | 16 | Mostly stable guides plus the mkdocstrings-backed reference pages |
| Partially aligned | 10 | Core behavior is right, but wording/examples are stale or incomplete in a few places |
| Incorrect | 2 | `cli/doctor.md` and `cli/stats.md` materially diverge from current behavior |
| Missing narrative coverage | 1 capability | `ditto lock` / `ditto.lock` are only discoverable through API reference, not the user-facing CLI/guides |

## Highest-priority issues

1. **`ditto lock` is not documented in the narrative CLI docs.** The command exists in `src/ditto/cli.py:330-347`, the plugin exposes `--ditto-lock` in `src/ditto/plugin.py:575-583`, and the lockfile implementation lives in `src/ditto/_lockfile.py:29-178`, but the authored CLI nav/pages stop at `run`, `update`, `prune`, `list`, `status`, `clean`, `recorders`, `doctor`, `lint`, and `stats` (`docs/mkdocs.yml:43-54`, `docs/src/cli/index.md:7-18`). The built API reference does expose `cmd_lock`, but only there (`docs/site/reference/cli/index.html:2194-2206`).
2. **`docs/src/cli/doctor.md` does not match what `ditto doctor` actually checks.** The page says backend plugins are checked (`docs/src/cli/doctor.md:14-20`), but `_doctor_checks()` only inspects `pytest11`, `ditto_recorders`, and `ditto_marks` entry points (`src/ditto/cli.py:533-570`, `tests/ci/test_cli_commands.py:85-166`).
3. **`ditto doctor` likely has a real implementation bug surfaced by this review.** It looks for a `pytest11` entry point named `ditto` (`src/ditto/cli.py:545-550`), but the package registers `recording = "ditto.plugin"` (`pyproject.toml:47-48`). That means the health check can report a false failure even on a normal install.
4. **The snapshot naming examples under-document the module prefix.** File-backed snapshots are stored as `module.group@key.ext` (`src/ditto/snapshot.py:171-179`, `tests/ci/test_snapshot_key.py:66-96`), so `docs/src/guides/snapshot-fixture.md:70-79` is missing the `tests.` prefix in its concrete example. `DittoTestCase` similarly uses `group_name=".".join(self.id().split(".")[-3:])` (`src/ditto/_unittest.py:29-33`, `tests/ci/test_unittest.py:29-33`), so `docs/src/guides/unittest.md:29-31` understates the stored identifier.
5. **Several CLI pages are too local-filesystem-centric for the current remote/custom-backend support.** `list`, `status`, and especially `stats` describe local files/directories, but the implementation works from backend manifests keyed by canonical URI (`src/ditto/_manifest.py:13-29`, `src/ditto/cli.py:640-678`) and explicitly supports remote/custom backends (`docs/src/cli/index.md:20-36`, `tests/ci/test_cli.py:250-261`).
6. **`docs/src/guides/custom-recorders.md` misstates the `ditto_marks` contract.** The guide implies the entry point value is the mark namespace object itself (`docs/src/guides/custom-recorders.md:57-68`), but `load_mark_plugins()` calls `ep.load()()` and therefore expects a zero-arg callable returning that object (`src/ditto/recorders/_plugins.py:36-59`, `tests/ci/test_plugins.py:110-130`).

## Detailed review

### Top-level pages

| Doc page | Related code/tests | Verdict | Findings |
|---|---|---|---|
| `docs/src/index.md` | `src/ditto/plugin.py:356-434`<br>`pyproject.toml:35-37,50-57`<br>`examples/README.md:95-100` | Partial | The recorder/fixture/CLI overview is accurate. The “PostgreSQL, Redis, DuckDB — anywhere” claim (`index.md:15-22`) is capability-true, but it reads like built-in support; the repo examples explicitly say those schemes are registered in example-local `conftest.py` files because the package does **not** ship installable `ditto_backends` plugins for them. |
| `docs/src/getting-started.md` | `src/ditto/plugin.py:514-543`<br>`src/ditto/snapshot.py:171-215`<br>`pyproject.toml:35-37` | Aligned | Installation, first-run behavior, built-in recorder marks, and `ditto update` usage all match current code. The examples are representative and consistent with the fixture implementation. |

### Guides

| Doc page | Related code/tests | Verdict | Findings |
|---|---|---|---|
| `docs/src/guides/snapshot-fixture.md` | `src/ditto/plugin.py:514-543,788-953`<br>`src/ditto/snapshot.py:171-201`<br>`tests/ci/test_snapshot_key.py:66-96` | Partial | Core fixture behavior, duplicate-key detection, and update/prune guidance are correct. The concrete file-path example at `snapshot-fixture.md:70-79` is stale for file-backed storage: `_flat_key()` prefixes the rootdir-relative module, so the example should include `tests.test_api...`, not just `test_api...`. The page also explains only the flat file-backed key shape even though non-file targets use `module/group@key.ext`. |
| `docs/src/guides/recorders.md` | `src/ditto/__init__.py:6-20`<br>`src/ditto/recorders/_pickle.py`<br>`src/ditto/recorders/_yaml.py`<br>`src/ditto/recorders/_json.py`<br>`pyproject.toml:35-37,50-53`<br>`tests/ci/test_recorders.py:21-99` | Aligned | Built-in recorder names, extensions, defaults, and plugin package names match the code and tests. The pandas/PyArrow alias tables match the expected registry keys and extensions. |
| `docs/src/guides/custom-recorders.md` | `src/ditto/recorders/_protocol.py`<br>`src/ditto/recorders/_plugins.py:36-59`<br>`src/ditto/__init__.py:23-56`<br>`tests/ci/test_plugins.py:110-130` | Partial | The recorder object contract is documented correctly. The `ditto_marks` section is not: the entry point example at `custom-recorders.md:62-68` reads as if the entry point target is the mark namespace object, but the loader requires a callable returning that object. |
| `docs/src/guides/backends.md` | `src/ditto/plugin.py:121-506`<br>`tests/ci/test_plugin_helpers.py:188-258`<br>`tests/ci/test_profiles.py:1-220`<br>`tests/ci/test_redis_backend.py:93-207` | Aligned | Target/profile precedence, `ditto_storage_options`, static vs fixture profiles, mutual-exclusion rules, and backend resolution order all match current code. The warning that profiles are self-contained is especially important and matches `_resolve_target()`. |
| `docs/src/guides/custom-backends.md` | `src/ditto/plugin.py:71-88,356-434,717-723,955-957`<br>`tests/ci/test_plugin_helpers.py:163-258`<br>`tests/ci/test_redis_backend.py:24-83` | Partial | The backend factory contract, URI registration model, and example adapters are correct. The context-manager timing text (`custom-backends.md:51-55`) is slightly off: context-managed backends are entered lazily on first resolution and then kept open for the rest of the session, not entered eagerly at session start. |
| `docs/src/guides/unittest.md` | `src/ditto/_unittest.py:15-34`<br>`tests/ci/test_unittest.py:21-72` | Partial | The local `.ditto/` backend behavior and the lack of per-method mark support are documented correctly. The storage-name wording is too simple: `DittoTestCase` uses `test_file.stem` plus the last three dotted `self.id()` components, so stored keys are typically closer to `test_module.TestClass.test_method@key.pkl` than the shorter `TestFn.test_fn` example suggests. |
| `docs/src/guides/upgrading.md` | `src/ditto/snapshot.py:171-201`<br>`src/ditto/plugin.py:476-482` | Aligned | The file-key flattening change, class-name inclusion, and `ditto_backend` migration guidance all match current behavior. The warning about silent re-recording on first post-upgrade run is accurate. |

### CLI pages

| Doc page | Related code/tests | Verdict | Findings |
|---|---|---|---|
| `docs/src/cli/index.md` | `docs/mkdocs.yml:43-54`<br>`src/ditto/cli.py:261-347`<br>`src/ditto/_cli_introspect.py:21-46` | Partial | The overview of remote-backend introspection is accurate and useful. The command table and nav omit `ditto lock`, even though the command exists and is part of the CLI surface. |
| `docs/src/cli/run.md` | `src/ditto/cli.py:261-277` | Aligned | Behavior is correct: all extra args are forwarded straight to pytest and the normal session report renders afterward. The usage block is illustrative rather than a literal Click signature, but the examples all work. |
| `docs/src/cli/update.md` | `src/ditto/cli.py:280-298`<br>`src/ditto/plugin.py:520-540` | Aligned | The command semantics match the implementation: encountered snapshots are overwritten, new ones are created normally, and all extra args are forwarded to pytest. |
| `docs/src/cli/prune.md` | `src/ditto/cli.py:301-327`<br>`src/ditto/plugin.py:815-953` | Aligned | The behavior and partial-run warning are consistent with the two-pass prune logic. The docs correctly warn that filtered runs can misclassify unused snapshots. |
| `docs/src/cli/list.md` | `src/ditto/cli.py:79-91,350-400`<br>`src/ditto/_manifest.py:13-29`<br>`tests/ci/test_cli.py:234-247,201-208` | Partial | The command does list snapshots, but the descriptions are a little too file/local oriented. The “Test” column is the parsed group portion of the storage key and may include module/class prefixes; the “Modified” column can be `—` for backends without mtime metadata, so it is not always a last-modified date. |
| `docs/src/cli/status.md` | `src/ditto/cli.py:449-467`<br>`tests/ci/test_cli.py:188-208` | Partial | Aggregate counts and recorder breakdowns are correct. The docs overstate date availability: oldest/newest are omitted when entries do not carry mtimes (for example remote/custom backends enumerated with `modified=None`), and “size on disk” is local-filesystem wording for a command that also summarizes remote values. |
| `docs/src/cli/clean.md` | `src/ditto/cli.py:403-446` | Aligned | The command is accurately documented: it finds local `.ditto/` directories, previews them, optionally prompts, and never touches remote backends. |
| `docs/src/cli/recorders.md` | `src/ditto/cli.py:117-135,470-511` | Partial | The overall behavior is right, but the documented output header is off. The rendered third column is titled `Source`, not `Package`, even though it does contain the source package name. |
| `docs/src/cli/doctor.md` | `src/ditto/cli.py:533-570`<br>`pyproject.toml:47-48`<br>`tests/ci/test_cli_commands.py:85-166` | Incorrect | The page says backend plugins are checked, but the implementation only checks pytest importability, one `pytest11` registration probe, recorder entry points, and mark entry points. It also appears to look for the wrong `pytest11` entry-point name (`ditto` vs the package’s `recording`), so the documented promise is not just stale; the command may currently misreport a healthy install. |
| `docs/src/cli/lint.md` | `src/ditto/cli.py:573-596`<br>`tests/ci/test_cli_commands.py:177-224` | Partial | Unknown extensions and empty files are documented correctly. The naming check is overstated: the implementation only detects a missing `@`, not the full expected filename structure. |
| `docs/src/cli/stats.md` | `src/ditto/cli.py:640-678`<br>`src/ditto/_manifest.py:23-29`<br>`tests/ci/test_cli.py:250-261` | Incorrect | The page describes per-`.ditto`-directory file counts. The implementation groups by resolved backend `location` (often `file://...`, `s3://...`, `redis://...`), includes empty configured backends so they remain visible, and labels the count column `Snapshots`, not `Files`. This page would currently mislead anyone using remote/custom targets. |

### API reference pages

| Doc page | Related code/tests | Verdict | Findings |
|---|---|---|---|
| `docs/src/reference/index.md` | `docs/mkdocs.yml:55-63` | Aligned | The module list matches the intended public reference surface. Internal helper modules remain intentionally out of scope. |
| `docs/src/reference/ditto.md` | `src/ditto/__init__.py:1-56` | Aligned | Mkdocstrings-backed page; low drift risk. It reflects the public exports (`Snapshot`, `DittoTestCase`, `DuplicateSnapshotKeyError`, and built-in marks) plus dynamic plugin-mark lookup via `__getattr__`. |
| `docs/src/reference/snapshot.md` | `src/ditto/snapshot.py:15-220` | Aligned | Mkdocstrings-backed page; low drift risk. The source docstrings accurately describe flat-vs-namespaced key formats and snapshot identity. |
| `docs/src/reference/recorders.md` | `src/ditto/recorders/__init__.py`<br>`src/ditto/recorders/_protocol.py`<br>`src/ditto/recorders/_plugins.py` | Aligned | Mkdocstrings-backed page; low drift risk. Good source of truth for the recorder protocol and registries. |
| `docs/src/reference/backends.md` | `src/ditto/backends/__init__.py`<br>`src/ditto/backends/_fsspec.py`<br>`src/ditto/backends/_prefix.py`<br>`src/ditto/backends/_transform.py` | Aligned | Mkdocstrings-backed page; low drift risk. It is accurate for the backend classes and registries exposed by the package. |
| `docs/src/reference/plugin.md` | `src/ditto/plugin.py:121-953` | Aligned | Mkdocstrings-backed page; low drift risk. This is currently the only authored-source page that exposes `--ditto-lock` and the plugin hooks in generated form. |
| `docs/src/reference/exceptions.md` | `src/ditto/exceptions.py` | Aligned | Mkdocstrings-backed page; low drift risk. Exception coverage matches the current hierarchy. |
| `docs/src/reference/cli.md` | `src/ditto/cli.py:1-678`<br>`docs/site/reference/cli/index.html:2194-2206` | Aligned | Mkdocstrings-backed page; low drift risk. The built docs confirm that `cmd_lock` does appear here even though the narrative CLI pages do not cover it. |

## Underdocumented functionality

| Functionality | Current doc coverage | Related code/tests | Verdict | Concern |
|---|---|---|---|---|
| `ditto lock`, `--ditto-lock`, `ditto.lock` rebuild semantics | Only indirectly covered through auto-generated API reference (`reference/cli.md`, `reference/plugin.md`) | `src/ditto/cli.py:330-347`<br>`src/ditto/plugin.py:575-583,788-809`<br>`src/ditto/_lockfile.py:29-178`<br>`tests/ci/test_lockfile.py`<br>`tests/ci/test_lockfile_session.py` | Missing narrative coverage | This is a substantive user-facing feature with safety constraints (“full run”, filtered-run refusal, committed lockfile expectations), but there is no guide or CLI page that explains when to use it. |

## Suggested documentation fixes

1. Add a dedicated `docs/src/cli/lock.md` page and include it in `docs/mkdocs.yml`; add at least one narrative guide section explaining `ditto.lock`, full-run requirements, and expected workflow.
2. Correct `docs/src/cli/doctor.md` to describe the current checks, or change the implementation so it really does inspect backend plugins and uses the actual `pytest11` registration name.
3. Fix the concrete snapshot-name examples in `guides/snapshot-fixture.md` and `guides/unittest.md` so they include the real module/group composition used by the code.
4. Update `guides/custom-recorders.md` so `ditto_marks` examples point to a zero-arg factory returning the mark namespace.
5. Rewrite `cli/stats.md`, `cli/status.md`, and `cli/list.md` to describe backend-manifest/URI-based output rather than assuming local `.ditto/` directories and universal mtime metadata.
6. Adjust smaller CLI wording mismatches (`recorders` column label, `lint` naming-check scope, homepage wording around non-built-in database backends).
