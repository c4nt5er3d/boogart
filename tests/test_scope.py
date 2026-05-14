from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state
from boogart.runtime import heartbeat
from boogart.world.scanner import scan_tree
from boogart.world.scope import ROOM_MARKER, allowed_roots


class ScopeTests(unittest.TestCase):
    def test_marked_scope_finds_short_boog_rooms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            docs = root / "Documents"
            marked = docs / "Nest"
            for folder in (desktop, marked):
                folder.mkdir(parents=True)
            (marked / ROOM_MARKER).write_text("", encoding="utf-8")

            paths = make_paths(root)
            state = BoogartState.new("jay")
            state.wander_scope = "marked"

            roots = allowed_roots(paths, state)

            self.assertIn(desktop, roots)
            self.assertIn(marked, roots)

    def test_home_rooms_tree_scan_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "Documents"
            deep = docs / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (docs / "near.txt").write_text("", encoding="utf-8")
            (deep / "too_deep.txt").write_text("", encoding="utf-8")

            observations = scan_tree((docs,), max_depth=2)
            names = {item.name for item in observations}

            self.assertIn("near.txt", names)
            self.assertNotIn("too_deep.txt", names)

    def test_heartbeat_stores_bounded_scope_tree_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            for folder in (paths.desktop, paths.documents, paths.data_dir):
                folder.mkdir(parents=True)
            (paths.documents / "code.py").write_text("", encoding="utf-8")
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.wander_scope = "home_rooms"
            save_state(paths.state_file, state)

            heartbeat(paths)
            saved = load_state(paths.state_file)
            scope_tree = saved.global_memory["scope_tree"]

            self.assertIn(str(paths.documents), scope_tree["roots"])
            self.assertGreaterEqual(scope_tree["observation_count"], 1)


def make_paths(root: Path) -> BoogartPaths:
    return BoogartPaths(
        home=root,
        desktop=root / "Desktop",
        documents=root / "Documents",
        downloads=root / "Downloads",
        pictures=root / "Pictures",
        music=root / "Music",
        videos=root / "Videos",
        data_dir=root / "Data",
        state_file=root / "Data" / "state.json",
        log_file=root / "Desktop" / "boogart_log.txt",
        desktop_boogart_png=root / "Desktop" / "boogart.png",
    )


if __name__ == "__main__":
    unittest.main()
