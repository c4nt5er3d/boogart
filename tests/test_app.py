from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from boogart.app import install_boogart
from boogart.core.paths import BoogartPaths
from boogart.core.state import load_state


class AppInstallTests(unittest.TestCase):
    def test_install_does_not_drop_first_launch_dialogue_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)

            with patch("boogart.app.BoogartPaths.discover", return_value=paths):
                state = install_boogart("jay")

            self.assertTrue(paths.desktop_boogart_png.exists())
            self.assertFalse((paths.desktop / "hey jay.txt").exists())
            self.assertNotIn("hey jay.txt", "\n".join(state.generated_files))

    def test_install_starts_with_quiet_log_and_message_cooldowns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)

            with patch("boogart.app.BoogartPaths.discover", return_value=paths):
                install_boogart("jay")

            saved = load_state(paths.state_file)
            log = paths.log_file.read_text(encoding="utf-8")

            self.assertIn("status: present", log)
            self.assertNotIn("name known", log)
            self.assertNotIn("mrrp", log)
            self.assertIn("vocalize", saved.memory["message_cooldowns"])
            self.assertIn("watcher", saved.memory["message_cooldowns"])


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
