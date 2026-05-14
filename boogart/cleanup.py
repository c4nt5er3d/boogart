from __future__ import annotations

import argparse
from pathlib import Path

from boogart.core.paths import BoogartPaths
from boogart.core.state import load_state


def cleanup(paths: BoogartPaths | None = None) -> list[Path]:
    current_paths = paths or BoogartPaths.discover()
    removed: list[Path] = []

    if current_paths.state_file.exists():
        state = load_state(current_paths.state_file)
        for value in list(state.generated_files):
            path = Path(value)
            if path.exists() and path.is_file():
                path.unlink()
                removed.append(path)

    for path in (current_paths.state_file,):
        if path.exists() and path.is_file():
            path.unlink()
            removed.append(path)

    if current_paths.data_dir.exists() and not any(current_paths.data_dir.iterdir()):
        current_paths.data_dir.rmdir()
        removed.append(current_paths.data_dir)

    return removed


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
