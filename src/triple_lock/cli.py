"""CLI entry point for the ``triple-lock-build`` command."""

import argparse
import os
import stat
import unicodedata
from pathlib import Path

from .config import DASHBOARD_COPY, OUTPUT, SCENARIO_DIR


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="The adjusted Triple Lock against the triple lock: every figure from full PolicyEngine UK runs"
    )
    parser.add_argument("--workers", type=int, default=3, help="concurrent primary Microcosm model processes; start with 1 until peak memory is measured")
    parser.add_argument("--sensitivity-workers", type=int, default=1,
                        help="concurrent Enhanced FRS 1.58.2 sensitivity model processes")
    parser.add_argument("--allow-dirty", action="store_true", help="build from a tree with uncommitted changes")
    parser.add_argument("--uncertainty-ruling", choices=("a", "b", "c"),
                        help="record Max's d955 ruling: a scenario envelope, b model-conditional expected value, "
                             "c suspended-treatment screen")
    parser.add_argument("--uncertainty-handoff", help="directory containing ts_uncertainty's handoff.json")
    parser.add_argument("--pre-budget", action="store_true",
                        help="write an interim pre-Budget file (requires --uncertainty-ruling a or c): a shows scenarios "
                             "only; c shows a provisional model-conditional expected value with C2 dry-run checks "
                             "and the paired dataset cross-check, "
                             "until the binding post-Budget score (docs/REBUILD.md, Interim pre-Budget release)")
    parser.add_argument("--mean-path-scenarios", action="store_true",
                        help="run only paired ±0.5pp mean-path scenarios, independently of C1 adequacy")
    parser.add_argument("--scenario", metavar="NAME",
                        help="only rerun one scenario (obr_premium; a full build runs them all) and write it, records "
                             "redacted, to --out, not the results file")
    parser.add_argument("--without-mean-paths", action="store_true",
                        help="write a scenarios-first interim file to --out: every run of the full build except the "
                             "paired mean paths, with the same jobs, so the full build reuses them (needs ruling a, "
                             "or c on a binding handoff whose primary failed C2; docs/REBUILD.md, Scenarios first)")
    parser.add_argument("--out", help="where --scenario writes its run (default data/scenarios/NAME.json), or where "
                                      "--without-mean-paths writes its interim file (required)")
    args = parser.parse_args(argv)
    if args.scenario and args.mean_path_scenarios:
        parser.error("choose either --scenario or --mean-path-scenarios")
    if args.without_mean_paths and (args.scenario or args.mean_path_scenarios or args.pre_budget):
        parser.error("--without-mean-paths is a full build's interim file, not --scenario, --mean-path-scenarios "
                     "or --pre-budget")
    if args.without_mean_paths and not args.out:
        parser.error("--without-mean-paths requires --out: the interim file never replaces the results file")
    if args.out and not (args.scenario or args.mean_path_scenarios or args.without_mean_paths):
        parser.error("--out requires --scenario NAME, --mean-path-scenarios or --without-mean-paths")
    if args.pre_budget and (args.scenario or args.mean_path_scenarios):
        parser.error("--pre-budget labels a full build's results file, not --scenario or --mean-path-scenarios")
    if args.pre_budget and args.uncertainty_ruling not in ("a", "c"):
        parser.error("--pre-budget requires --uncertainty-ruling a or c; b is obsolete (c: provisional, on the C2 dry run)")
    if args.pre_budget and args.uncertainty_handoff:
        parser.error("--pre-budget generates its own scenario design; it takes no --uncertainty-handoff")

    if args.mean_path_scenarios:
        from pathlib import Path
        from .jobs import terminate_on_signals
        from .pipeline import mean_path_scenarios, write
        out = Path(args.out) if args.out else SCENARIO_DIR / "mean_paths.json"
        if overwrite_refusal(out):
            parser.error("--mean-path-scenarios must not overwrite the results file or dashboard copy")
        with terminate_on_signals():
            write(mean_path_scenarios(workers=args.workers, allow_dirty=args.allow_dirty,
                                      uncertainty_ruling=args.uncertainty_ruling,
                                      handoff_path=args.uncertainty_handoff), [out])
        return 0

    if args.scenario:
        return scenario(args.scenario, args.out, args.allow_dirty)

    from pathlib import Path
    from .jobs import terminate_on_signals
    from .pipeline import build, write

    if args.without_mean_paths:
        out = Path(args.out)
        if refused := interim_refusal(out):
            parser.error(f"--without-mean-paths {refused}")
    # SIGTERM or SIGHUP stops the running model processes before the build exits (jobs.run_jobs, run_child).
    with terminate_on_signals():
        results, scenarios = build(workers=args.workers, allow_dirty=args.allow_dirty,
                                   sensitivity_workers=args.sensitivity_workers,
                                   uncertainty_ruling=args.uncertainty_ruling,
                                   uncertainty_handoff=args.uncertainty_handoff, pre_budget=args.pre_budget,
                                   mean_paths=not args.without_mean_paths)
        if args.without_mean_paths:  # the full build writes the results file and the scenario files
            write_interim(results, out)
            return 0
        write(results, [OUTPUT, DASHBOARD_COPY])
        for name, run in scenarios.items():  # one rebuild refreshes every scenario run too
            write(run, [SCENARIO_DIR / f"{name}.json"])
    return 0


PUBLICATION = "must not write the results file, its dashboard copy or a scenario file"


def _fold(name):
    """A name as a case- and normalisation-insensitive volume (APFS, macOS's default) compares it."""
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", name).casefold())


def _identity(status):
    return status.st_dev, status.st_ino


def _status(path, **kwargs):
    try:
        return os.stat(path, **kwargs)
    except OSError:
        return None


def _same_entry(a, b):
    """Whether two paths name one file or directory: by identity when both exist, otherwise by their resolved
    spellings, folded, so a case alias of a file that doesn't exist yet still counts as that file."""
    first, second = _status(a), _status(b)
    if first and second:
        return _identity(first) == _identity(second)
    return _fold(os.path.realpath(a)) == _fold(os.path.realpath(b))


def destination(out):
    """The entry a write to ``out`` replaces: its directory resolved as the OS resolves it (each symbolic link
    followed before any '..' after it), its final name kept. None when ``out`` names no file ('', '.', '..')."""
    out = Path(out)
    if out.name in ("", ".", ".."):
        return None
    return Path(os.path.realpath(out.parent)) / out.name


def _protected_file(entry):
    """Whether ``entry`` (a destination()) is the results file or its dashboard copy, by identity or alias."""
    return any(_same_entry(entry, protected) or (_same_entry(entry.parent, protected.parent)
                                                 and _fold(entry.name) == _fold(protected.name))
               for protected in (OUTPUT, DASHBOARD_COPY))


def overwrite_refusal(out):
    """For --scenario and --mean-path-scenarios, which may write the scenario directory: why ``out`` cannot be
    written (it is the results file or its dashboard copy, by identity or alias), or None."""
    entry = destination(out)
    if entry is None:
        return f"must not write {out}: it names a directory, not a file"
    if _protected_file(entry):
        return "must not overwrite the results file or its dashboard copy"
    return None


def interim_refusal(out, hardlinks=True):
    """Why ``out`` cannot take a scenarios-first interim file, or None.

    The file must not be, or share an inode with, a publication output: the results file, its dashboard copy or any
    file under the scenario directory. Paths are compared by file identity, not spelling, so a case alias on a
    case-insensitive volume (data/RESULTS.JSON) or a symbolic link to a directory counts as the file it names, and
    a symbolic link followed by '..' counts as where the OS takes it. The destination entry itself must not be a
    symbolic link, since the write replaces the entry. A destination that already has a second name (a hardlink)
    is refused outright, since writing it in place would change the file behind the other name too;
    ``hardlinks=False`` skips that check, for write_interim, whose rename leaves any other name alone.
    """
    entry = destination(out)
    if entry is None:
        return f"must not write {out}: it names a directory, not a file"
    if entry.is_symlink():
        return f"must not write {entry}: it is a symbolic link, and the write would replace it"
    if any(_same_entry(d, SCENARIO_DIR) for d in (entry.parent, *entry.parent.parents)):
        return PUBLICATION
    if _protected_file(entry):
        return PUBLICATION
    if hardlinks and entry.exists() and entry.stat().st_nlink > 1:
        return f"must not write {entry}: it has {entry.stat().st_nlink} names (a hardlink), so the write would change another file"
    return None


def _ancestors(directory):
    """Identities of an open directory and of every directory above it, found by walking '..' from the handle."""
    found, handle = [], os.dup(directory)
    try:
        while (here := _identity(os.fstat(handle))) not in found:
            found.append(here)
            parent = os.open("..", os.O_RDONLY | os.O_DIRECTORY, dir_fd=handle)
            os.close(handle)
            handle = parent
    finally:
        os.close(handle)
    return found


def _under_scenarios(directory):
    """Whether an open directory is the scenario directory or inside it, by the identities of its ancestors."""
    scenarios = _status(SCENARIO_DIR)
    return bool(scenarios) and _identity(scenarios) in _ancestors(directory)


def _open_directory(path, created):
    """A handle on the resolved directory ``path``, opening each component through the handle above it and creating
    a missing one there. No component may be a symbolic link (O_NOFOLLOW), and none is created inside the scenario
    directory, so a directory swapped for a link during the write gets no new subdirectory where it points. Each
    directory it makes goes on ``created`` as (handle on its parent, name, identity), for _release to remove if the
    write fails."""
    parts = Path(path).parts
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    handle = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=handle)
            except FileNotFoundError:
                if _under_scenarios(handle):
                    raise SystemExit(f"--without-mean-paths {PUBLICATION}")
                os.mkdir(part, dir_fd=handle)
                child = os.open(part, flags, dir_fd=handle)
                try:
                    made = _identity(os.fstat(child))  # before the dup, so a failed fstat leaves no handle open
                    created.append((os.dup(handle), part, made))
                except BaseException:
                    os.close(child)
                    raise
            os.close(handle)
            handle = child
    except BaseException:
        os.close(handle)
        raise
    return handle


def _release(created, remove):
    """Close the parent handles _open_directory kept; first, if ``remove``, try to remove the directories it
    recorded, deepest first, only while empty and only while the name each was made under still holds it. A
    recorded directory goes wherever its parent moves, so it is removed there. One that was itself moved or renamed
    is not found, and stays behind, empty. The identity check has three gaps, each of which can remove another
    process's empty directory: a swap between the mkdir and the open after it (the walk then records theirs), a swap
    between the check and the removal, and a file system that reuses a removed directory's identity."""
    for parent, name, made in reversed(created):
        try:
            if remove and _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) == made:
                os.rmdir(name, dir_fd=parent)
        except OSError:
            pass
        finally:
            os.close(parent)


def _handle_refusal(directory, name):
    """interim_refusal for the directory the write holds open, by the identities of the handle, its ancestors and
    the entry, so a path changed after the check cannot redirect the write."""
    if _under_scenarios(directory):
        return PUBLICATION
    entry = _status(name, dir_fd=directory, follow_symlinks=False)
    if entry and stat.S_ISLNK(entry.st_mode):
        return f"must not write {name}: it is a symbolic link, and the write would replace it"
    here = _identity(os.fstat(directory))
    for protected in (OUTPUT, DASHBOARD_COPY):
        file, folder = _status(protected), _status(protected.parent)
        if ((entry and file and _identity(entry) == _identity(file))
                or (folder and _identity(folder) == here and _fold(name) == _fold(protected.name))):
            return PUBLICATION
    return None


def write_interim(results, out):
    """Write the interim file as a new inode and rename it over ``out``, so no other name for the old file changes.

    The text is pipeline.write's. A hardlink made to ``out`` during the build keeps the old contents. The guard runs
    again on the path, then on the destination directory held open (_open_directory creates any missing part through
    handles): the temporary file and the rename go through that handle (openat, renameat), so no path is looked up
    again after the check. After the rename the guard checks the handle once more and unlinks the file if the
    directory moved into the scenario directory meanwhile, or if that check itself fails; should the unlink fail
    too, the file stays and its error propagates. A failed or refused write tries to remove the empty directories
    _open_directory recorded, within the limits _release names. A directory made just before a failure that stopped
    its record (the open, fstat or dup after the mkdir) goes unrecorded and stays, empty. A directory moved into the
    scenario directory and back between two checks, or moved there after the last one, is beyond what a check can
    see.
    """
    import json
    import secrets

    from .pipeline import validate_write_paths

    (out,) = validate_write_paths(results, [out])
    if refused := interim_refusal(out, hardlinks=False):  # again: the destination may have changed during the build
        raise SystemExit(f"--without-mean-paths {refused}")
    entry = destination(out)
    text = json.dumps(results, indent=1, default=float, allow_nan=False) + "\n"
    created, written = [], False
    try:
        directory = _open_directory(entry.parent, created)
    except BaseException:
        _release(created, remove=True)
        raise
    try:
        if refused := _handle_refusal(directory, entry.name):
            raise SystemExit(f"--without-mean-paths {refused}")
        temporary = f".{entry.name}.{secrets.token_hex(6)}.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=directory)
        try:
            try:
                stream = os.fdopen(descriptor, "w", encoding="utf-8")
            except BaseException:
                os.close(descriptor)
                raise
            with stream:
                stream.write(text)
            os.rename(temporary, entry.name, src_dir_fd=directory, dst_dir_fd=directory)  # rename(2) replaces
            try:
                moved = _under_scenarios(directory)  # did the directory move into the scenario directory?
            except BaseException:
                os.unlink(entry.name, dir_fd=directory)  # unchecked: fail closed
                raise
            if moved:
                os.unlink(entry.name, dir_fd=directory)
                raise SystemExit(f"--without-mean-paths {PUBLICATION}")
            written = True
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            raise
    finally:
        try:
            os.close(directory)
        finally:
            _release(created, remove=not written)
    print(f"Results written to {entry}")


def scenario(name, out=None, allow_dirty=False):
    """One scenario run (pipeline.scenario), written to ``out``; never to the results file or its dashboard copy."""
    from pathlib import Path

    from .jobs import terminate_on_signals
    from .pipeline import scenario as run_scenario
    from .pipeline import write
    from .trajectories import SCENARIOS

    if name not in SCENARIOS:
        raise SystemExit(f"unknown scenario {name!r}: one of {sorted(SCENARIOS)}")
    out = Path(out) if out else SCENARIO_DIR / f"{name}.json"
    if overwrite_refusal(out):
        raise SystemExit("--scenario must not overwrite the results file or its dashboard copy")
    with terminate_on_signals():
        write(run_scenario(name, allow_dirty=allow_dirty), [out])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
