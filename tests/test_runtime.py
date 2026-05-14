from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state, state_from_dict
from boogart.runtime import heartbeat


class RuntimeTests(unittest.TestCase):
    def test_state_loader_migrates_old_save_shape(self) -> None:
        state = state_from_dict({"username": "jay", "phase": "kitten"})

        self.assertEqual(state.username, "jay")
        self.assertEqual(state.lifecycle, "alive")
        self.assertEqual(state.stage, "newborn")
        self.assertEqual(state.current_folder, "")

    def test_heartbeat_ticks_saves_logs_and_renders(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            data = root / "Data"
            desktop.mkdir()
            data.mkdir()
            paths = BoogartPaths(
                home=root,
                desktop=desktop,
                documents=root / "Documents",
                downloads=root / "Downloads",
                pictures=root / "Pictures",
                music=root / "Music",
                videos=root / "Videos",
                data_dir=data,
                state_file=data / "state.json",
                log_file=desktop / "boogart_log.txt",
                desktop_boogart_png=desktop / "boogart.png",
            )
            state = BoogartState.new("jay")
            state.current_folder = str(desktop)
            save_state(paths.state_file, state)

            result = heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(result.action_id, "vocalize")
            self.assertTrue((desktop / "boogart.png").exists())
            self.assertIn("boogart.png", "\n".join(saved.generated_files))
            self.assertIn("[day 1 / boogart / newborn] mrrp", paths.log_file.read_text(encoding="utf-8"))

    def test_heartbeat_message_director_suppresses_repeated_vocalize(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            data = root / "Data"
            desktop.mkdir()
            data.mkdir()
            paths = BoogartPaths(
                home=root,
                desktop=desktop,
                documents=root / "Documents",
                downloads=root / "Downloads",
                pictures=root / "Pictures",
                music=root / "Music",
                videos=root / "Videos",
                data_dir=data,
                state_file=data / "state.json",
                log_file=desktop / "boogart_log.txt",
                desktop_boogart_png=desktop / "boogart.png",
            )
            state = BoogartState.new("jay")
            state.current_folder = str(desktop)
            save_state(paths.state_file, state)

            heartbeat(paths, now)
            heartbeat(paths, now + timedelta(minutes=1))

            lines = paths.log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(sum(1 for line in lines if "mrrp" in line), 1)


if __name__ == "__main__":
    unittest.main()
