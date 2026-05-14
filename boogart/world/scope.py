from __future__ import annotations

from pathlib import Path

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState


ROOM_MARKER = ".boog"
VALID_SCOPES = {"desktop", "marked", "home_rooms"}


def allowed_roots(paths: BoogartPaths, state: BoogartState) -> tuple[Path, ...]:
    scope = state.wander_scope if state.wander_scope in VALID_SCOPES else "desktop"
    if scope == "desktop":
        return (paths.desktop,)
    if scope == "home_rooms":
        return paths.common_home_rooms()

    roots = {paths.desktop}
    roots.update(find_marked_rooms(paths.common_home_rooms()))
    return tuple(sorted(roots, key=lambda path: str(path).lower()))


def find_marked_rooms(roots: tuple[Path, ...], max_depth: int = 2, max_dirs: int = 300) -> set[Path]:
    marked: set[Path] = set()
    seen = 0
    for root in roots:
        if not root.exists():
            continue
        for folder in bounded_folders(root, max_depth=max_depth):
            seen += 1
            if seen > max_dirs:
                return marked
            if (folder / ROOM_MARKER).exists():
                marked.add(folder)
    return marked


def bounded_folders(root: Path, max_depth: int) -> list[Path]:
    folders = [root]
    if max_depth <= 0:
        return folders

    for child in safe_iterdir(root):
        if child.is_dir() and not is_hidden_or_systemish(child):
            folders.extend(bounded_folders(child, max_depth - 1))
    return folders


def is_allowed_path(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def is_hidden_or_systemish(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith(".") or name in {"appdata", "program files", "program files (x86)", "windows", "system32", "library"}


def safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []
