from __future__ import annotations

from pathlib import Path

from boogart.core.lifecycle import track_generated_file
from boogart.core.state import BoogartState
from boogart.world.scope import is_allowed_path


OWNED_FILENAMES = {
    "boogart.png",
    "boogart_log.txt",
    "dead_boogart.png",
    "stain_boogart.png",
}


class FilePolicyError(RuntimeError):
    pass


class FileSystemAdapter:
    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.roots = roots

    def assert_allowed(self, path: Path) -> None:
        if not is_allowed_path(path, self.roots):
            raise FilePolicyError(f"path outside allowed roots: {path}")

    def write_owned_text(self, state: BoogartState, path: Path, text: str) -> Path:
        self.assert_allowed(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        track_generated_file(state, path)
        return path

    def delete_food(self, path: Path) -> None:
        self.assert_allowed(path)
        if path.suffix.lower() != ".food":
            raise FilePolicyError(f"refusing to delete non-food file: {path}")
        if path.exists():
            path.unlink()

    def delete_owned(self, state: BoogartState, path: Path) -> None:
        self.assert_allowed(path)
        if not self.is_owned(state, path):
            raise FilePolicyError(f"refusing to delete unowned file: {path}")
        if path.exists():
            path.unlink()

    def replace_owned(self, state: BoogartState, source: Path, target: Path) -> Path:
        self.assert_allowed(source)
        self.assert_allowed(target)
        if not self.is_owned(state, source):
            raise FilePolicyError(f"refusing to replace unowned file: {source}")
        if source.exists():
            source.replace(target)
        track_generated_file(state, target)
        return target

    def is_owned(self, state: BoogartState, path: Path) -> bool:
        return path.name in OWNED_FILENAMES or str(path) in state.generated_files
