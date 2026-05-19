from __future__ import annotations
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from boogart.runtime import run_heartbeat, HeartbeatFrame, RuntimeConfig
from boogart.core.state import BoogartState, save_state, load_state
from boogart.core.paths import BoogartPaths

class MovementCleanupTests(unittest.TestCase):
    def test_renamed_body_is_cleaned_up_on_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = root / "Desktop"
            other = desktop / "Subfolder"
            desktop.mkdir(parents=True)
            other.mkdir()
            
            paths = BoogartPaths(
                home=root, desktop=desktop, documents=root/"Docs",
                downloads=root/"Downloads", pictures=root/"Pics",
                music=root/"Music", videos=root/"Vids",
                data_dir=root/"Data", state_file=root/"Data"/"state.json",
                lock_file=root/"Data"/"boogart.lock",
                tether_file=root/".boogart_tether",
                debug_file=root/"Data"/"debug.txt", log_file=desktop/"log.txt",
                desktop_boogart_png=desktop/"boogart.png"
            )
            paths.data_dir.mkdir(parents=True)
            
            # Setup state with a renamed body
            state = BoogartState.new("jay")
            state.current_folder = str(desktop)
            state.body_name = "renamed_boogart.png"
            # Ensure move triggers immediately
            now = datetime.now(timezone.utc)
            state.next_move_at = (now - timedelta(seconds=1)).isoformat(timespec="seconds")
            state.birth_time = (now - timedelta(days=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)
            
            # Create the renamed body file
            renamed_file = desktop / "renamed_boogart.png"
            renamed_file.write_text("body", encoding="utf-8")
            
            # Force movement to 'other' by mocking candidates
            # Subfolder of desktop will have a positive weight
            with unittest.mock.patch('boogart.runtime.movement_candidates', return_value=[other]):
                run_heartbeat(paths, now, config=RuntimeConfig(dev_fast=True))
            
            # Verify old file is gone
            self.assertFalse(renamed_file.exists(), f"Old renamed body {renamed_file} should have been unlinked")
            
            # Verify new file exists in the new location
            new_state = load_state(paths.state_file)
            self.assertEqual(new_state.current_folder, str(other))
            self.assertTrue((other / "boogart.png").exists(), "New body should exist at destination")

if __name__ == "__main__":
    unittest.main()
