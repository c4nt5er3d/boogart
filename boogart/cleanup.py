from __future__ import annotations

import argparse
import os
from pathlib import Path

from boogart.core.debug import debug_log
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state


CORE_FILENAMES = {
    "boogart.png",
    "boogart_dead.png",
    "boogart_husk.png",
    "boogart.lock",
    "log.txt",
}


def cleanup(paths: BoogartPaths | None = None) -> list[Path]:
    current_paths = paths or BoogartPaths.discover()
    removed: list[Path] = []
    candidates: list[Path] = [
        current_paths.desktop_boogart_png,
        current_paths.log_file,
        current_paths.desktop / "boogart_dead.png",
        current_paths.desktop / "boogart_husk.png",
        current_paths.debug_file,
        current_paths.lock_file,
        current_paths.state_file,
        current_paths.tether_file,
        current_paths.desktop / ".was_here",
        current_paths.downloads / ".was_here",
    ]

    if current_paths.state_file.exists():
        state = load_state(current_paths.state_file)
        candidates.extend(Path(value) for value in list(state.generated_files))
        candidates.extend(Path(value) for value in list(state.manifest))
        current_folder = Path(state.current_folder or current_paths.desktop)
        candidates.extend(
            [
                current_folder / state.body_name,
                current_folder / "boogart.png",
                current_folder / "boogart_dead.png",
                current_folder / "boogart_husk.png",
                current_folder / ".was_here",
            ]
        )
    else:
        state = None

    for path in unique_paths(candidates):
        if path.exists() and path.is_file() and is_cleanup_candidate(path, current_paths, state):
            try:
                path.unlink()
                removed.append(path)
            except OSError as exc:
                debug_log(current_paths, "cleanup_unlink_failed", path=path, error=exc)

    for path in (current_paths.state_file, current_paths.debug_file, current_paths.lock_file):
        if path.exists() and path.is_file():
            try:
                path.unlink()
                removed.append(path)
            except OSError as exc:
                debug_log(current_paths, "cleanup_unlink_failed", path=path, error=exc)

    if current_paths.data_dir.exists() and not any(current_paths.data_dir.iterdir()):
        current_paths.data_dir.rmdir()
        removed.append(current_paths.data_dir)

    return removed


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        value = str(path)
        if value not in seen:
            seen.add(value)
            unique.append(path)
    return unique


def is_cleanup_candidate(path: Path, paths: BoogartPaths, state: BoogartState | None = None) -> bool:
    if path == paths.debug_file:
        return True
    if path in {paths.state_file, paths.lock_file, paths.tether_file}:
        return True
    if path.name in CORE_FILENAMES:
        return True
    if state and path.name == state.body_name:
        return True
    if state:
        generated = {str(value) for value in [*state.generated_files, *state.manifest]}
        if str(path) in generated and is_generated_path_in_scope(path, paths):
            return True
    return False


def is_generated_path_in_scope(path: Path, paths: BoogartPaths) -> bool:
    if path == paths.tether_file:
        return True
    return any(is_within(path, root) for root in (paths.desktop, paths.downloads, paths.data_dir))


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove Boogart-generated files and local state.")
    parser.add_argument("--yes", action="store_true", help="run without asking for confirmation")
    args = parser.parse_args()

    paths = BoogartPaths.discover()
    if paths.lock_file.exists() and not stale_lock_removed(paths):
        print("boogart seems to be running.")
        print("please stop boogart before cleaning up.")
        return

    if not args.yes:
        answer = input("remove Boogart's generated files and state? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            print("left everything alone.")
            return

    removed = cleanup()
    if not removed:
        print("nothing to remove.")
        return

    print("removed:")
    for path in removed:
        print(f"- {path}")


def stale_lock_removed(paths: BoogartPaths) -> bool:
    try:
        raw_pid = paths.lock_file.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
    except (OSError, ValueError):
        return remove_lock(paths)
    if pid <= 0 or not pid_is_running(pid):
        return remove_lock(paths)
    return False


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def remove_lock(paths: BoogartPaths) -> bool:
    try:
        paths.lock_file.unlink()
    except FileNotFoundError:
        return True
    except OSError as exc:
        debug_log(paths, "cleanup_stale_lock_remove_failed", error=exc)
        return False
    debug_log(paths, "cleanup_stale_lock_removed", path=paths.lock_file)
    return True


if __name__ == "__main__":
    main()
