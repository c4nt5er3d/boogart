from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from boogart.cleanup import cleanup
from boogart.core.lifecycle import track_generated_file
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, save_state


class CleanupTests(unittest.TestCase):
    def test_cleanup_removes_only_tracked_generated_files_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            data = root / "Data"
            desktop.mkdir()
            data.mkdir()
            paths = make_paths(root)
            state = BoogartState.new("jay")
            generated = desktop / "boogart.png"
            user_file = desktop / "keep.txt"
            generated.write_text("boogart", encoding="utf-8")
            user_file.write_text("mine", encoding="utf-8")
            track_generated_file(state, generated)
            save_state(paths.state_file, state)

            removed = cleanup(paths)

            self.assertIn(generated, removed)
            self.assertFalse(generated.exists())
            self.assertTrue(user_file.exists())
            self.assertFalse(paths.state_file.exists())


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
