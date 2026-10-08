---
name: pytest-ditto
description: Write, debug, and maintain pytest-ditto snapshot tests, including the snapshot fixture, @ditto recorder marks, snapshot mismatches, ditto.lock, and the ditto CLI (update, verify, lock, prune, clean). Use in projects that depend on pytest-ditto or when a task requests it.
license: MIT
---

# pytest-ditto

Use this skill for projects consuming pytest-ditto. Its workflows describe the
2.x implementation shipped alongside this skill. For another version, check its
documentation and command help before applying version-specific behavior.

## Establish the relevant context

Use the project's existing Python environment and test runner. Before running
tests, inspect the relevant pytest configuration, installed ditto version,
recorder selection, and storage targets or profiles. Check command help when a
flag may be unavailable. Read only the references needed for the task.

Preserve the configured target and project conventions. A request to fix a
snapshot test does not imply migrating its storage, replacing its recorder, or
upgrading dependencies. If execution is unavailable, inspect the artifacts and
report the commands that remain unverified.

## Write an assertion that tests the intended contract

`snapshot(value, key=...)` returns a value; it does not assert equality. The
test must compare the current result with that value. Use distinct, descriptive
keys within a test and stable parametrization IDs.

Choose a recorder and comparison function that preserve the tested behavior.
Read [assertions and recorders](references/assertions-and-recorders.md) for
strict JSON, specialized data types, or serialization and comparison failures.

Keep normalization limited to fields outside the tested contract. Preserve
ordering, types, metadata, and values when they are meaningful. Fix unstable
inputs at their source when possible.

## Decide whether the baseline should change

Normal pytest runs can record missing snapshots and append entries to
`ditto.lock`. A passing first recording does not establish that its contents are
correct. Review newly recorded values against the requested behavior.

Before updating an existing baseline, establish why the changed output is
expected. Proceed when the authorized task establishes that change. Investigate
unexplained differences before replacing their baselines. If expected behavior
remains ambiguous, ask a targeted question and continue independent diagnosis.

Scope `ditto update` to the affected tests: every snapshot the run reaches is
overwritten. Review every created or changed snapshot and lock entry, including
untracked files. For binary formats, compare loaded values, schema, and metadata.
A passing update run alone does not validate the new baseline.

## Maintain ownership and verify

Use `ditto verify` to check existing baselines without writing snapshots or the
lock. It still runs test bodies. Your assertions compare values; verify also
checks storage against the lock, only in targets the run exercises. State the
scope of a filtered run or a run that exercises no snapshot targets.

Verify, lock, and prune require a single process. If pytest configuration enables
xdist distribution, pass `-n 0` in an environment with pytest-xdist installed.

Read [baselines and the lock](references/baselines-and-lock.md) before rebuilding
ownership, pruning, cleaning, or migrating baselines. Let ditto generate snapshot
identities and lock entries; the reference explains the target-retirement
exception. Keep baseline updates and deletions within the authorized task.

Read [backends](references/backends.md) when remote storage, profiles,
credentials, live inventory, or shared targets affect the task. Do not add
`--shared` merely to make a prune failure pass.

## Finish with evidence

After recording or updating, review baseline contents against the intended
behavior and run the relevant tests without update flags. Use verify when lock
and storage consistency is part of the task. Broaden to the full configured suite
when ownership maintenance requires it.

Report what changed, why baselines changed, the commands and results, and any
limited verification scope or checks that could not run. Respect existing
authorization; ask for a missing decision or permission only when it affects the
next action.
