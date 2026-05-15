from __future__ import annotations

import argparse
from pathlib import Path

from boogart.core.paths import BoogartPaths
from boogart.core.state import load_state


CORE_FILENAMES = {
    "boogart.png",
    "boogart_dead.png",
    "boogart_husk.png",
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
    ]

    if current_paths.state_file.exists():
        state = load_state(current_paths.state_file)
        candidates.extend(Path(value) for value in list(state.generated_files))
        current_folder = Path(state.current_folder or current_paths.desktop)
        candidates.extend(
            [
                current_folder / state.body_name,
                current_folder / "boogart.png",
                current_folder / "boogart_dead.png",
                current_folder / "boogart_husk.png",
            ]
        )

    for path in unique_paths(candidates):
        if path.exists() and path.is_file() and is_cleanup_candidate(path, current_paths):
            path.unlink()
            removed.append(path)

    for path in (current_paths.state_file, current_paths.debug_file):
        if path.exists() and path.is_file():
            path.unlink()
            removed.append(path)

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


def is_cleanup_candidate(path: Path, paths: BoogartPaths) -> bool:
    if path == paths.debug_file:
        return True
    return path.name in CORE_FILENAMES


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove Boogart-generated files and local state.")
    parser.add_argument("--yes", action="store_true", help="run without asking for confirmation")
    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
