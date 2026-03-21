from pathlib import Path

import pytest

from ditto import Snapshot
from ditto.recorders import Recorder, RECORDER_REGISTRY, default as _default_recorder
from ditto.exceptions import AdditionalMarkError, DittoMarkHasNoIOType
from ditto.snapshot import session_tracker


__all__ = ("snapshot",)


_DEFAULT_OUTPUT_DIR_NAME = ".ditto"


def _resolve_recorder(marks: list) -> Recorder:
    """
    Resolve the recorder from a list of pytest marks.

    Parameters
    ----------
    marks : list
        Collected pytest marks named `record` from the test node.

    Returns
    -------
    Recorder
        The recorder corresponding to the mark, or the pickle recorder when
        no mark is present.

    Raises
    ------
    AdditionalMarkError
        If more than one `record` mark is present on the test.
    DittoMarkHasNoIOType
        If the mark carries no arguments or names a recorder that is not
        registered — making unknown format strings an explicit error rather
        than a silent fallback to pickle.
    """
    match len(marks):
        case 0:
            return _default_recorder()
        case 1:
            if not marks[0].args or marks[0].args[0] not in RECORDER_REGISTRY:
                raise DittoMarkHasNoIOType()
            return RECORDER_REGISTRY[marks[0].args[0]]
        case _:
            raise AdditionalMarkError()


def _snapshot_dir(test_path: Path) -> Path:
    """
    Return the `.ditto` directory path adjacent to the given test file.

    Parameters
    ----------
    test_path : Path
        Path to the test file.

    Returns
    -------
    Path
        The `.ditto` directory that sits alongside the test file.
    """
    return test_path.parent / _DEFAULT_OUTPUT_DIR_NAME


def pytest_addoption(parser):
    group = parser.getgroup("ditto")
    group.addoption(
        "--ditto-update",
        action="store_true",
        default=False,
        help="Overwrite all existing snapshots with current test values.",
    )
    group.addoption(
        "--ditto-prune",
        action="store_true",
        default=False,
        help="After the session, delete snapshot files not accessed during this run.",
    )


@pytest.fixture
def snapshot(request) -> Snapshot:
    marks = list(request.node.iter_markers(name="record"))
    recorder = _resolve_recorder(marks)
    path = _snapshot_dir(request.path)
    path.mkdir(exist_ok=True)
    update = request.config.getoption("--ditto-update", default=False)
    return Snapshot(path=path, group_name=request.node.name, recorder=recorder, update=update)


def pytest_sessionstart(session):
    session_tracker.reset()


def pytest_sessionfinish(session, exitstatus):
    from ditto._report import render_session_report

    config = session.config
    do_prune = config.getoption("--ditto-prune", default=False)

    pruned: list[Path] = []
    unused: list[Path] = []

    if do_prune or session_tracker.accessed:
        rootdir = Path(config.rootdir)
        all_ditto_files = set(rootdir.rglob(".ditto/*"))
        # Only consider actual files (not directories inside .ditto/)
        all_ditto_files = {p for p in all_ditto_files if p.is_file()}
        not_accessed = all_ditto_files - session_tracker.accessed

        if do_prune:
            for fp in sorted(not_accessed):
                fp.unlink()
                pruned.append(fp)
        else:
            unused = sorted(not_accessed)

    render_session_report(
        created=session_tracker.created,
        updated=session_tracker.updated,
        pruned=pruned,
        unused=unused,
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "record(recorder): snapshot values")
