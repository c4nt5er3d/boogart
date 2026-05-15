from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from boogart.app import install_boogart
from boogart.cleanup import cleanup
from boogart.core.debug import debug_status
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state, state_from_dict
from boogart.rendering.sprite import render_boogart_sprite
from boogart.runtime import HeartbeatFrame, RuntimeConfig, movement_candidates, run_heartbeat, run_simulation


class GddRuntimeTests(unittest.TestCase):
    def test_install_creates_only_body_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            with patch("boogart.app.BoogartPaths.discover", return_value=paths):
                state = install_boogart("jay")

            self.assertTrue((paths.desktop / "boogart.png").exists())
            self.assertTrue((paths.desktop / "log.txt").exists())
            self.assertEqual(sorted(path.name for path in paths.desktop.iterdir()), ["boogart.png", "log.txt"])
            self.assertEqual(state.phase, 1)
            self.assertIn("mrrp", paths.log_file.read_text(encoding="utf-8"))

    def test_food_is_eaten_from_roaming_scope_without_reading_contents(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            (paths.downloads / "anything.food").write_text("do not matter", encoding="utf-8")
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.hunger = 80
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten")
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertIn("ate:anything.food", frame.events)
            self.assertFalse((paths.downloads / "anything.food").exists())
            self.assertLess(saved.hunger, 80)

    def test_log_is_capped_at_three_entries_per_day(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.hunger = 99
            state.neglect = 1
            state.next_hunger_at = now.isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten")
            save_state(paths.state_file, state)

            for offset in range(5):
                run_heartbeat(paths, now + timedelta(minutes=offset * 2))

            lines = paths.log_file.read_text(encoding="utf-8").splitlines()
            self.assertLessEqual(len(lines), 3)

    def test_deleted_body_leaves_dead_png(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)

            self.assertIn("dead:absence", frame.events)
            self.assertTrue((paths.desktop / "boogart_dead.png").exists())
            self.assertEqual(load_state(paths.state_file).lifecycle, "dead")

    def test_cleanup_removes_manifest_files_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            with patch("boogart.app.BoogartPaths.discover", return_value=paths):
                install_boogart("jay")

            removed = cleanup(paths)

            self.assertIn(paths.state_file, removed)
            self.assertFalse(paths.state_file.exists())
            self.assertFalse(paths.desktop_boogart_png.exists())
            self.assertFalse(paths.log_file.exists())

    def test_cleanup_removes_orphan_desktop_files_without_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            paths.desktop_boogart_png.write_text("orphan body", encoding="utf-8")
            paths.log_file.write_text("orphan log", encoding="utf-8")
            paths.debug_file.write_text("debug", encoding="utf-8")

            cleanup(paths)

            self.assertFalse(paths.desktop_boogart_png.exists())
            self.assertFalse(paths.log_file.exists())
            self.assertFalse(paths.debug_file.exists())

    def test_cleanup_removes_current_folder_body_even_if_manifest_missed_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            nested = paths.desktop / "New Folder" / "runtime"
            nested.mkdir(parents=True)
            paths.data_dir.mkdir()
            body = nested / "boogart.png"
            body.write_text("body", encoding="utf-8")
            state = BoogartState.new("jay")
            state.current_folder = str(nested)
            state.generated_files = []
            save_state(paths.state_file, state)

            cleanup(paths)

            self.assertFalse(body.exists())
            self.assertFalse(paths.state_file.exists())

    def test_dev_fast_simulation_advances_without_waiting_real_days(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            now = datetime.fromisoformat(load_state(paths.state_file).birth_time)

            result = run_simulation(
                paths,
                ticks=8,
                step=timedelta(minutes=10),
                start=now,
                config=RuntimeConfig(dev_fast=True),
            )
            saved = load_state(paths.state_file)

            self.assertEqual(result.ticks, 8)
            self.assertGreaterEqual(saved.phase, 2)
            self.assertTrue((Path(saved.current_folder) / saved.body_name).exists())

    def test_first_heartbeat_keeps_boogart_visible_on_desktop(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            nested = paths.desktop / "New Folder" / "runtime" / "java-runtime-delta"
            nested.mkdir(parents=True)
            state = load_state(paths.state_file)
            state.birth_time = now.isoformat(timespec="seconds")
            state.next_move_at = now.isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertNotIn("moved:java-runtime-delta", frame.events)
            self.assertEqual(Path(saved.current_folder), paths.desktop)
            self.assertTrue(paths.desktop_boogart_png.exists())

    def test_first_day_candidates_exclude_deep_runtime_but_later_allow_it(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            nested = paths.desktop / "New Folder" / "runtime" / "java-runtime-delta"
            nested.mkdir(parents=True)
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.birth_time = now.isoformat(timespec="seconds")

            early_frame = HeartbeatFrame(paths=paths, now=now + timedelta(hours=1), state=state)
            later_frame = HeartbeatFrame(paths=paths, now=now + timedelta(hours=25), state=state)

            self.assertNotIn(nested, movement_candidates(early_frame))
            self.assertIn(nested, movement_candidates(later_frame))

    def test_windows_discovery_prefers_known_desktop_over_userprofile_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            visible_desktop = root / "OneDrive" / "Desktop"
            fallback_desktop = root / "Profile" / "Desktop"
            visible_desktop.mkdir(parents=True)

            def known_folder(name: str) -> Path | None:
                return visible_desktop if name == "Desktop" else None

            with (
                patch("boogart.core.paths.sys.platform", "win32"),
                patch("boogart.core.paths.Path.home", return_value=root / "Profile"),
                patch.dict("boogart.core.paths.os.environ", {"USERPROFILE": str(root / "Profile"), "APPDATA": str(root / "AppData")}, clear=True),
                patch("boogart.core.paths.windows_known_folder", side_effect=known_folder),
            ):
                paths = BoogartPaths.discover()

            self.assertEqual(paths.desktop, visible_desktop)
            self.assertNotEqual(paths.desktop, fallback_desktop)

    def test_state_loader_accepts_legacy_string_phase(self) -> None:
        state = state_from_dict({"username": "jay", "phase": "kitten"})

        self.assertEqual(state.phase, 1)

    def test_debug_status_reports_paths_and_recent_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)

            status = debug_status(paths)

            self.assertIn("BOOGART DEBUG STATUS", status)
            self.assertIn(str(paths.desktop), status)
            self.assertIn("install_render_body", status)
            self.assertIn("boogart.png", status)
            self.assertIn("current_body_path", status)
            self.assertIn("current_body_exists: True", status)


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
        debug_file=root / "Data" / "debug.txt",
        log_file=root / "Desktop" / "log.txt",
        desktop_boogart_png=root / "Desktop" / "boogart.png",
    )


if __name__ == "__main__":
    unittest.main()
