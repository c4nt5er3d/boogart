from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state
from boogart.runtime import heartbeat
from boogart.world.scanner import scan_folder
from boogart.world.watcher import snapshot_folder, update_watcher_memory


class WatcherTests(unittest.TestCase):
    def test_watcher_comments_on_shallow_folder_changes(self) -> None:
        state = BoogartState.new("jay")

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            place, observations = scan_folder(folder)
            update_watcher_memory(state, snapshot_folder(place, observations))

            (folder / "notes_final_FINAL.txt").write_text("", encoding="utf-8")
            place, observations = scan_folder(folder)
            comments = update_watcher_memory(state, snapshot_folder(place, observations))

            self.assertIn("another ending appeared.", comments)

    def test_heartbeat_watches_current_folder_only(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            current = root / "Current"
            other = root / "Other"
            data = root / "Data"
            for folder in (desktop, current, other, data):
                folder.mkdir()
            (other / "private_final_FINAL.txt").write_text("", encoding="utf-8")

            paths = BoogartPaths(
                desktop=desktop,
                data_dir=data,
                state_file=data / "state.json",
                log_file=desktop / "boogart_log.txt",
                desktop_boogart_png=desktop / "boogart.png",
            )
            state = BoogartState.new("jay")
            state.current_folder = str(current)
            save_state(paths.state_file, state)

            heartbeat(paths, now)
            saved = load_state(paths.state_file)
            snapshots = saved.global_memory["folder_snapshots"]

            self.assertIn(str(current), snapshots)
            self.assertNotIn(str(other), snapshots)
            self.assertNotIn("private_final_FINAL", paths.log_file.read_text(encoding="utf-8"))

    def test_quiet_hour_comment_increases_corruption_without_clipboard(self) -> None:
        now = datetime(2026, 1, 1, 3, 30, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            data = root / "Data"
            desktop.mkdir()
            data.mkdir()
            paths = BoogartPaths(
                desktop=desktop,
                data_dir=data,
                state_file=data / "state.json",
                log_file=desktop / "boogart_log.txt",
                desktop_boogart_png=desktop / "boogart.png",
            )
            state = BoogartState.new("jay")
            state.current_folder = str(desktop)
            save_state(paths.state_file, state)

            heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(saved.corruption, 1)
            self.assertIn("quiet hour", paths.log_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
