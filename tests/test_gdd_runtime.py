from __future__ import annotations

import tempfile
import unittest
import io
import os
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from boogart.app import boogart_lock, install_boogart, run_watch_heartbeat_loop, tk_runtime_safe
from boogart.cleanup import cleanup
from boogart.core.debug import debug_status
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state, state_from_dict
from boogart.rendering.png import read_png_metadata
from boogart.rendering.sprite import render_boogart_sprite
from boogart.runtime import HeartbeatFrame, RuntimeConfig, artifact_metadata, body_metadata, call_boogart, corpse_metadata, movement_candidates, pet_boogart, run_heartbeat, run_simulation
from boogart.ui.terminal import render_live_panel
from boogart.ui.watch import BoogartWatchWindow, WatchUnavailableError, open_folder


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

    def test_installed_body_png_has_identity_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            state = install_boogart("jay", paths)

            metadata = read_png_metadata(paths.desktop_boogart_png)

            self.assertEqual(metadata["boogart_id"], state.boogart_id)
            self.assertEqual(metadata["generation"], "1")
            self.assertEqual(metadata["stage"], "kitten")
            self.assertEqual(metadata["boogart_artifact"], "body")
            self.assertEqual(metadata["not_body"], "false")

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

            # Heartbeat 1: Notice
            run_heartbeat(paths, now)

            # Heartbeat 2: Eat
            frame = run_heartbeat(paths, now + timedelta(seconds=2))
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

            self.assertIn("dead:deleted", frame.events)
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

    def test_live_panel_renders_boogart_status(self) -> None:
        now = datetime(2026, 1, 1, 8, 15, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            state = BoogartState.new("jay")
            state.hunger = 73
            state.affection = 7
            paths.log_file.write_text("[2026-01-01T08:01:00+00:00]: found warm folder\n", encoding="utf-8")

            panel = render_live_panel(paths, state, ["moved", "txt:hair.txt"], now)

            self.assertIn("BOOGART LIVE", panel)
            self.assertIn("hunger:", panel)
            self.assertIn("place:", panel)
            self.assertNotIn("wrongness", panel)
            self.assertNotIn("motion:", panel)
            self.assertIn("08:01", panel)
            self.assertIn("left hair.txt", panel)

    def test_hunger_100_does_not_kill_before_starvation_grace(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.birth_time = (now - timedelta(hours=3)).isoformat(timespec="seconds")
            state.last_active_at = (now - timedelta(minutes=15)).isoformat(timespec="seconds")
            state.hunger = 100
            state.neglect = 6
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_move_at = now.isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            state.body_hash = ""
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertNotIn("dead:starvation", frame.events)
            self.assertEqual(saved.lifecycle, "alive")
            self.assertEqual(saved.neglect, 0)
            self.assertIn("starving_since", saved.memory)

    def test_first_starvation_death_requires_active_time(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.birth_time = (now - timedelta(hours=4)).isoformat(timespec="seconds")
            state.last_active_at = (now - timedelta(minutes=60)).isoformat(timespec="seconds")
            state.hunger = 100
            state.next_hunger_at = (now + timedelta(days=10)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(days=10)).isoformat(timespec="seconds")
            state.memory["first_session_until"] = (now - timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["starving_since"] = (now - timedelta(hours=71)).isoformat(timespec="seconds")
            state.memory["active_starving_minutes"] = 71 * 60
            state.memory["active_minutes_total"] = 71 * 60
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            state.body_hash = ""
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertIn("dead:starvation", frame.events)
            self.assertEqual(saved.lifecycle, "dead")
            self.assertTrue((paths.desktop / "boogart_dead.png").exists())
            self.assertFalse(paths.desktop_boogart_png.exists())

    def test_feeding_resets_starvation_progress(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            (paths.downloads / "anything.food").write_text("x", encoding="utf-8")
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.birth_time = (now - timedelta(hours=4)).isoformat(timespec="seconds")
            state.hunger = 100
            state.next_hunger_at = (now + timedelta(days=1)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(days=1)).isoformat(timespec="seconds")
            state.memory["first_session_until"] = (now - timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["starving_since"] = (now - timedelta(hours=20)).isoformat(timespec="seconds")
            state.memory["active_starving_minutes"] = 20 * 60
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            run_heartbeat(paths, now)
            frame = run_heartbeat(paths, now + timedelta(minutes=15))
            saved = load_state(paths.state_file)

            self.assertIn("ate:anything.food", frame.events)
            self.assertNotIn("starving_since", saved.memory)
            self.assertEqual(saved.memory["active_starving_minutes"], 0)
            self.assertLessEqual(saved.hunger, 45)

    def test_copy_reaction_is_delayed_once_nondestructive_and_metadata_only(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=2)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            state.body_hash = ""
            copy_path = paths.downloads / "copy.png"
            render_boogart_sprite(copy_path, "kitten", metadata=body_metadata(state, "kitten"))
            false_positive = paths.downloads / "boogart fanart.png"
            render_boogart_sprite(false_positive, "kitten")
            save_state(paths.state_file, state)

            run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            scheduled = load_state(paths.state_file)
            first_after = scheduled.memory["copy_reaction_after"]
            self.assertEqual(scheduled.copy_count, 1)

            run_heartbeat(paths, now + timedelta(minutes=1), RuntimeConfig(dev_fast=True))
            rescheduled = load_state(paths.state_file)
            self.assertEqual(rescheduled.copy_count, 1)
            self.assertEqual(rescheduled.memory["copy_reaction_after"], first_after)

            run_heartbeat(paths, now + timedelta(minutes=8), RuntimeConfig(dev_fast=True))
            reacted = load_state(paths.state_file)
            self.assertTrue(copy_path.exists())
            self.assertTrue(false_positive.exists())
            self.assertTrue((paths.downloads / "not me.txt").exists())
            self.assertNotIn("copy_reaction_after", reacted.memory)

    def test_cleanup_removes_generated_side_files_tether_and_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            side_files = [
                paths.desktop / ".was_here",
                paths.desktop / "crumbs.png",
                paths.downloads / "not me.txt",
            ]
            paths.downloads.mkdir()
            for path in side_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x", encoding="utf-8")
                state.generated_files.append(str(path))
            paths.lock_file.write_text("0", encoding="utf-8")
            save_state(paths.state_file, state)

            cleanup(paths)

            for path in [*side_files, paths.tether_file, paths.lock_file, paths.state_file, paths.debug_file]:
                self.assertFalse(path.exists(), f"{path} should be removed")

    def test_stale_lock_is_recovered_but_live_lock_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.data_dir.mkdir(parents=True)
            paths.lock_file.write_text("999999999", encoding="utf-8")

            with boogart_lock(paths) as locked:
                self.assertTrue(locked)

            paths.lock_file.write_text("999999999", encoding="utf-8")
            with patch("boogart.app.pid_is_running", return_value=True):
                with boogart_lock(paths) as locked:
                    self.assertFalse(locked)

    def test_respawn_wins_over_husk_after_long_dead_period(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.lifecycle = "dead"
            state.memory["died_at"] = now.isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            run_heartbeat(paths, now + timedelta(hours=49), RuntimeConfig(dev_fast=False))
            saved = load_state(paths.state_file)

            self.assertEqual(saved.lifecycle, "alive")
            self.assertEqual(saved.body_name, "boogart.png")
            self.assertFalse((paths.desktop / "boogart_husk.png").exists())
            self.assertTrue((Path(saved.current_folder) / saved.body_name).exists())

    def test_txt_drop_is_hard_capped_at_one_per_day(self) -> None:
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.phase = 3
            state.txt_count_today = 1
            state.last_log_day = now.date().isoformat()
            state.next_txt_at = now.isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)

            self.assertFalse(any(event.startswith("txt:") for event in frame.events))

    def test_metadata_missing_trashed_body_can_be_recovered_by_hash(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            trash = root / ".Trash"
            trash.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.body_name = "boogart.png"
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            legacy_body = trash / "boogart.png"
            legacy_body.write_text("legacy body", encoding="utf-8")
            state.body_hash = __import__("hashlib").sha256(b"legacy body").hexdigest()
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(frame.body_path, legacy_body)
            self.assertEqual(Path(saved.current_folder), trash)

    def test_metadata_missing_body_hash_is_not_used_in_ordinary_folder(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.body_name = "boogart.png"
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            loose_copy = paths.downloads / "boogart.png"
            loose_copy.write_text("legacy body", encoding="utf-8")
            state.body_hash = __import__("hashlib").sha256(b"legacy body").hexdigest()
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertNotEqual(frame.body_path, loose_copy)
            self.assertEqual(saved.lifecycle, "dead")
            self.assertIn("dead:deleted", frame.events)

    def test_metadata_mismatched_body_kills_without_rendering_live_body(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            other = BoogartState.new("other")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(other, "kitten"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)

            self.assertIn("dead:absence", frame.events)
            self.assertFalse(paths.desktop_boogart_png.exists())
            self.assertTrue((paths.desktop / "boogart_dead.png").exists())

    @unittest.skipIf(os.name == "nt", "symlink creation requires extra Windows privileges")
    def test_live_body_symlink_is_ignored_without_following_target(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            target = root / "target.png"
            target.write_text("do not rewrite target", encoding="utf-8")
            os.symlink(target, paths.desktop_boogart_png)
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(saved.lifecycle, "dead")
            self.assertIn("dead:absence", frame.events)
            self.assertEqual(target.read_text(encoding="utf-8"), "do not rewrite target")

    def test_read_only_render_failure_is_debugged_without_crashing(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.birth_time = (now - timedelta(days=3)).isoformat(timespec="seconds")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            with patch("boogart.runtime.render_boogart_sprite", side_effect=PermissionError("locked")):
                frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(saved.lifecycle, "alive")
            self.assertTrue(any(event.startswith("state:") for event in frame.events))
            self.assertIn("render_body_failed", paths.debug_file.read_text(encoding="utf-8"))

    def test_clock_jump_backwards_does_not_advance_or_rewind_active_time(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        future = now + timedelta(days=2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.last_active_at = future.isoformat(timespec="seconds")
            state.next_move_at = (future + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_hunger_at = (future + timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["active_minutes_total"] = 10
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(saved.memory["active_minutes_total"], 10)
            self.assertEqual(saved.last_active_at, future.isoformat(timespec="seconds"))
            self.assertIn("clock_jump_detected_at", saved.memory)

    def test_archive_missing_body_enters_archived_then_recovers_on_extract(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)
            paths.desktop_boogart_png.unlink()
            (paths.desktop / "boogart.zip").write_bytes(b"not opened by boogart")

            archived = run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            archived_state = load_state(paths.state_file)
            panel = render_live_panel(paths, archived_state, archived.events, now)

            self.assertEqual(archived_state.lifecycle, "archived")
            self.assertIn("archived:boogart.zip", archived.events)
            self.assertNotIn("dead:deleted", archived.events)
            self.assertIn("age: folded", panel)
            self.assertIn("mood: bundled up", panel)

            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(archived_state, "kitten"))
            recovered = run_heartbeat(paths, now + timedelta(minutes=1), RuntimeConfig(dev_fast=True))
            recovered_state = load_state(paths.state_file)

            self.assertEqual(recovered_state.lifecycle, "alive")
            self.assertIn("unarchived", recovered.events)
            self.assertEqual(recovered_state.body_name, "boogart.png")

    def test_archive_grace_delays_deleted_death_then_expires(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)
            paths.desktop_boogart_png.unlink()
            (paths.desktop / "boogart.tar.gz").write_bytes(b"folded")

            run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            before = run_heartbeat(paths, now + timedelta(minutes=9), RuntimeConfig(dev_fast=True))
            before_state = load_state(paths.state_file)
            expired = run_heartbeat(paths, now + timedelta(minutes=11), RuntimeConfig(dev_fast=True))
            expired_state = load_state(paths.state_file)

            self.assertEqual(before_state.lifecycle, "archived")
            self.assertNotIn("dead:deleted", before.events)
            self.assertEqual(expired_state.lifecycle, "dead")
            self.assertIn("dead:deleted", expired.events)

    def test_residue_metadata_does_not_count_as_body_copy(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            render_boogart_sprite(paths.downloads / "lint.png", "residue", metadata=artifact_metadata(state, "residue", "nest"))
            save_state(paths.state_file, state)

            run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            saved = load_state(paths.state_file)

            self.assertEqual(saved.copy_count, 0)
            self.assertNotIn("copy_reaction_after", saved.memory)

    def test_artifact_named_like_body_is_not_recovered_as_live_body(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.downloads / "boogart.png", "residue", metadata=artifact_metadata(state, "residue", "nest"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertIn("dead:deleted", frame.events)
            self.assertEqual(saved.lifecycle, "dead")
            self.assertNotEqual(Path(saved.current_folder), paths.downloads)

    def test_renamed_artifact_is_not_recovered_as_live_body(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop / "lint.png", "residue", metadata=artifact_metadata(state, "residue", "nest"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertIn("dead:deleted", frame.events)
            self.assertEqual(saved.lifecycle, "dead")
            self.assertEqual(saved.body_name, "boogart.png")

    def test_note_filename_sequence_stops_before_random_allocator_names(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            for name in (
                "hello.txt",
                "is anyone there.txt",
                "i found something.txt",
                "the walls are thin.txt",
                "it's quiet here.txt",
                "don't leave yet.txt",
                "stay.txt",
                "where did you go.txt",
                "i'm still here.txt",
            ):
                (paths.desktop / name).write_text("old", encoding="utf-8")
            state = BoogartState.new("jay")
            state.phase = 4
            state.current_folder = str(paths.desktop)
            state.next_txt_at = now.isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))

            self.assertIn("txt:wait.txt", frame.events)
            self.assertFalse(any(" (" in path.name for path in paths.desktop.iterdir()))

    def test_latest_corpse_is_not_immediately_eaten_after_respawn(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            corpse = paths.desktop / "boogart_dead.png"
            render_boogart_sprite(corpse, "kitten_dead", metadata=body_metadata(state, "kitten_dead"))
            state.lifecycle = "dead"
            state.memory["died_at"] = now.isoformat(timespec="seconds")
            state.memory["death_corpse_path"] = str(corpse)
            state.memory["death_corpse_generation"] = state.generation
            state.hunger = 100
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            run_heartbeat(paths, now + timedelta(minutes=6), RuntimeConfig(dev_fast=True))
            frame = run_heartbeat(paths, now + timedelta(minutes=7), RuntimeConfig(dev_fast=True))
            saved = load_state(paths.state_file)

            self.assertTrue((paths.desktop / "boogart_dead.png").exists())
            self.assertTrue((paths.desktop / "boogart.png").exists())
            self.assertEqual(saved.body_name, "boogart.png")
            self.assertNotIn("ate_corpse:boogart_dead.png", frame.events)

    def test_old_corpse_takes_three_bites_without_changing_live_body_sprite(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.generation = 3
            state.hunger = 100
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            old_state = BoogartState.new("jay")
            old_state.boogart_id = state.boogart_id
            old_state.generation = 1
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            render_boogart_sprite(paths.desktop / "boogart_dead.png", "kitten_dead", metadata=corpse_metadata(old_state, "kitten_dead"))
            save_state(paths.state_file, state)

            notice = run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            bite_one = run_heartbeat(paths, now + timedelta(minutes=1), RuntimeConfig(dev_fast=True))
            after_one = read_png_metadata(paths.desktop / "boogart_dead.png")
            live_after_one = read_png_metadata(paths.desktop_boogart_png)
            bite_two = run_heartbeat(paths, now + timedelta(minutes=2), RuntimeConfig(dev_fast=True))
            after_two = read_png_metadata(paths.desktop / "boogart_dead.png")
            final_bite = run_heartbeat(paths, now + timedelta(minutes=3), RuntimeConfig(dev_fast=True))
            saved = load_state(paths.state_file)
            live_after_final = read_png_metadata(paths.desktop_boogart_png)

            self.assertNotIn("bit_corpse:boogart_dead.png:1/3", notice.events)
            self.assertIn("bit_corpse:boogart_dead.png:1/3", bite_one.events)
            self.assertEqual(after_one["corpse_bites"], "1")
            self.assertEqual(after_one["visual_state"], "kitten_dead_bite1")
            self.assertEqual(after_one["generation"], "1")
            self.assertEqual(live_after_one["stage"], "kitten")
            self.assertNotIn("visual_state", live_after_one)
            self.assertNotIn("blood_level", live_after_one)
            self.assertIn("bit_corpse:boogart_dead.png:2/3", bite_two.events)
            self.assertEqual(after_two["corpse_bites"], "2")
            self.assertEqual(after_two["visual_state"], "kitten_dead_bite2")
            self.assertIn("ate_corpse:boogart_dead.png", final_bite.events)
            self.assertFalse((paths.desktop / "boogart_dead.png").exists())
            self.assertEqual(saved.hunger, 20)
            self.assertEqual(saved.memory["corpse_bites"], 3)
            self.assertEqual(saved.memory["cannibal_blood_level"], 3)
            self.assertEqual(live_after_final["stage"], "kitten")
            self.assertNotIn("visual_state", live_after_final)
            self.assertNotIn("blood_level", live_after_final)

    def test_partial_corpse_bite_state_survives_restart_from_metadata(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.generation = 3
            state.hunger = 100
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            old_state = BoogartState.new("jay")
            old_state.boogart_id = state.boogart_id
            old_state.generation = 1
            corpse = paths.desktop / "boogart_dead.png"
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            render_boogart_sprite(corpse, "kitten_dead", metadata=corpse_metadata(old_state, "kitten_dead"))
            save_state(paths.state_file, state)

            run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            run_heartbeat(paths, now + timedelta(minutes=1), RuntimeConfig(dev_fast=True))
            restarted = load_state(paths.state_file)
            restarted.memory.pop("corpse_bite_counts", None)
            save_state(paths.state_file, restarted)
            frame = run_heartbeat(paths, now + timedelta(minutes=2), RuntimeConfig(dev_fast=True))

            self.assertIn("bit_corpse:boogart_dead.png:2/3", frame.events)
            self.assertEqual(read_png_metadata(corpse)["corpse_bites"], "2")

    def test_moved_or_copied_partial_corpse_keeps_bite_progress(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.generation = 3
            state.hunger = 100
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            old_state = BoogartState.new("jay")
            old_state.boogart_id = state.boogart_id
            old_state.generation = 1
            corpse = paths.downloads / "boogart_dead.png"
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            render_boogart_sprite(corpse, "kitten_dead_bite1", metadata=corpse_metadata(old_state, "kitten_dead", bites=1, visual_stage="kitten_dead_bite1"))
            save_state(paths.state_file, state)

            notice = run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            frame = run_heartbeat(paths, now + timedelta(minutes=1), RuntimeConfig(dev_fast=True))

            self.assertNotIn("bit_corpse:boogart_dead.png:2/3", notice.events)
            self.assertIn("bit_corpse:boogart_dead.png:2/3", frame.events)
            self.assertEqual(read_png_metadata(corpse)["corpse_bites"], "2")

    def test_trashed_body_is_recovered_without_death(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            trash = root / ".Trash"
            trash.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            body = trash / "boogart.png"
            render_boogart_sprite(body, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(saved.lifecycle, "alive")
            self.assertEqual(Path(saved.current_folder), trash)
            self.assertNotIn("dead:deleted", frame.events)

    def test_trashed_body_is_preferred_over_existing_copy(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            trash = root / ".Trash"
            trash.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            trash_body = trash / "boogart.png"
            existing_copy = paths.downloads / "boogart_copy.png"
            render_boogart_sprite(trash_body, "kitten", metadata=body_metadata(state, "kitten"))
            render_boogart_sprite(existing_copy, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(saved.lifecycle, "alive")
            self.assertEqual(Path(saved.current_folder), trash)
            self.assertEqual(saved.body_name, "boogart.png")

    def test_first_two_hours_have_hook_but_no_starvation_death(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.downloads.mkdir(parents=True)
            (paths.downloads / "first.food").write_text("x", encoding="utf-8")
            install_boogart("jay", paths)
            start = datetime.fromisoformat(load_state(paths.state_file).birth_time)

            events: list[str] = []
            for index in range(8):
                frame = run_heartbeat(paths, start + timedelta(minutes=15 * index), RuntimeConfig(dev_fast=False))
                events.extend(frame.events)

            saved = load_state(paths.state_file)
            self.assertEqual(saved.lifecycle, "alive")
            self.assertFalse(any(event.startswith("dead:starvation") for event in events))
            self.assertTrue(any(event == "moved" for event in events))
            self.assertTrue(any(event.startswith("ate:first.food") for event in events))
            self.assertTrue(paths.log_file.exists())

    def test_heartbeat_keeps_live_png_static_without_pose_events(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_txt_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["visual_pose"] = "idle1"
            render_boogart_sprite(paths.desktop_boogart_png, "kitten_idle1", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            metadata = read_png_metadata(paths.desktop_boogart_png)

            self.assertFalse(any(event.startswith("pose:") for event in frame.events))
            self.assertEqual(metadata["stage"], "kitten")
            self.assertNotIn("motion", metadata)
            self.assertNotIn("visual_state", metadata)
            self.assertEqual(sorted(path.name for path in paths.desktop.iterdir()), ["boogart.png"])

    def test_live_body_still_updates_for_growth_stage(self) -> None:
        now = datetime(2026, 1, 4, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.birth_time = (now - timedelta(days=3)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_txt_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            run_heartbeat(paths, now)
            metadata = read_png_metadata(paths.desktop_boogart_png)

            self.assertEqual(metadata["stage"], "cat")
            self.assertNotIn("motion", metadata)

    def test_first_visible_move_is_scheduled_in_steam_hook_window(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.birth_time = now.isoformat(timespec="seconds")
            state.next_move_at = now.isoformat(timespec="seconds")
            save_state(paths.state_file, state)

            run_heartbeat(paths, now)
            saved = load_state(paths.state_file)
            next_move = datetime.fromisoformat(saved.next_move_at)

            self.assertGreaterEqual(next_move, now + timedelta(minutes=8))
            self.assertLessEqual(next_move, now + timedelta(minutes=20))
            self.assertFalse(saved.memory.get("first_visible_move_done"))

    def test_delayed_food_waits_then_eats_after_delay(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.downloads.mkdir()
            paths.data_dir.mkdir()
            food = paths.downloads / "patient.food"
            food.write_text("x", encoding="utf-8")
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.hunger = 50
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["first_session_until"] = (now - timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["food_meals_total"] = 1
            state.memory["force_delayed_food"] = True
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            waiting = run_heartbeat(paths, now, RuntimeConfig(dev_fast=True))
            waiting_state = load_state(paths.state_file)
            wait_until = datetime.fromisoformat(str(waiting_state.memory["food_wait_until"]))
            before = run_heartbeat(paths, wait_until - timedelta(seconds=1), RuntimeConfig(dev_fast=True))
            eaten = run_heartbeat(paths, wait_until + timedelta(seconds=1), RuntimeConfig(dev_fast=True))

            self.assertIn("food_waiting:patient.food", waiting.events)
            self.assertIn("food_waiting:patient.food", before.events)
            self.assertIn("ate:patient.food", eaten.events)
            self.assertFalse(food.exists())

    def test_stray_event_creates_one_artifact_inside_scope(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["force_stray_event"] = True
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            first = run_heartbeat(paths, now)
            second = run_heartbeat(paths, now + timedelta(minutes=1))
            stray = paths.desktop / "second_body.png"
            metadata = read_png_metadata(stray)

            self.assertIn("stray:second_body.png", first.events)
            self.assertFalse(any(event.startswith("stray:") for event in second.events))
            self.assertTrue(stray.exists())
            self.assertEqual(metadata["boogart_artifact"], "stray")
            self.assertEqual(metadata["not_body"], "true")
            self.assertTrue(str(stray).startswith(str(paths.desktop)))

    def test_impossible_place_moves_once_to_deep_safe_folder(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            deep = paths.desktop / "ordinary" / "under"
            deep.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.memory["force_impossible_place"] = True
            render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertIn("impossible_moved", frame.events)
            self.assertEqual(Path(saved.current_folder), deep)
            self.assertTrue((deep / "boogart.png").exists())
            self.assertFalse(paths.desktop_boogart_png.exists())

    def test_watch_open_folder_uses_platform_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch("boogart.ui.watch.sys.platform", "darwin"), patch("boogart.ui.watch.subprocess.Popen") as popen:
                open_folder(folder)

            popen.assert_called_once_with(["open", str(folder)])

    def test_pet_action_updates_affection_without_extra_files(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            before_files = sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

            result = pet_boogart(paths, now)
            saved = load_state(paths.state_file)
            after_files = sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

            self.assertIn("pet:soft", result.events)
            self.assertEqual(saved.affection, 1)
            self.assertEqual(before_files, after_files)

    def test_call_action_answers_next_heartbeat_without_extra_files(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_hunger_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            state.next_txt_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            save_state(paths.state_file, state)
            before_files = sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

            result = call_boogart(paths, now)
            called = load_state(paths.state_file)
            frame = run_heartbeat(paths, now + timedelta(minutes=1))
            after_files = sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())

            self.assertIn("call:heard", result.events)
            self.assertTrue(called.memory.get("call_pending"))
            self.assertIn("call:heard", frame.events)
            self.assertFalse(load_state(paths.state_file).memory.get("call_pending"))
            self.assertEqual(before_files, after_files)

    def test_pyside_watch_window_instantiates_with_mocked_qt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            install_boogart("jay", paths)
            window = BoogartWatchWindow(
                paths,
                RuntimeConfig(dev_fast=True),
                qt_modules=fake_qt_modules(),
                app=FakeApplication(),
            )

            self.assertEqual(window.window.title, "Boogart")
            self.assertEqual(window.hunger_bar.minimum, 0)
            self.assertEqual(window.hunger_bar.maximum, 100)
            window.toggle_pause()
            self.assertTrue(window.paused)
            self.assertEqual(window.pause_button.text, "Resume")
            window.quit()
            self.assertTrue(window.window.closed)
            self.assertTrue(window.app.quit_called)

    def test_watch_window_falls_back_to_live_panel_if_unavailable_in_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            with (
                patch("boogart.app.tk_runtime_safe", return_value=True),
                patch("boogart.ui.watch.run_watch_window", side_effect=WatchUnavailableError("no display")),
                patch("boogart.app.stdout_interactive", return_value=True),
                patch("boogart.app.run_live_heartbeat_loop") as live,
            ):
                with redirect_stdout(io.StringIO()):
                    run_watch_heartbeat_loop(paths, RuntimeConfig(dev_fast=True))

            live.assert_called_once()

    def test_watch_window_falls_back_to_background_loop_if_unavailable_without_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = make_paths(Path(tmp))
            with (
                patch("boogart.app.tk_runtime_safe", return_value=True),
                patch("boogart.ui.watch.run_watch_window", side_effect=WatchUnavailableError("no display")),
                patch("boogart.app.stdout_interactive", return_value=False),
                patch("boogart.app.run_heartbeat_loop") as background,
            ):
                with redirect_stdout(io.StringIO()):
                    run_watch_heartbeat_loop(paths, RuntimeConfig(dev_fast=True))

            background.assert_called_once()

    def test_macos_command_line_tools_python_skips_tk_runtime(self) -> None:
        with (
            patch("boogart.app.sys.platform", "darwin"),
            patch("boogart.app.sys.executable", "/Library/Developer/CommandLineTools/usr/bin/python3"),
            patch("boogart.app.sys.base_prefix", "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9"),
            patch("boogart.app.sys.version_info", (3, 9, 6)),
        ):
            self.assertFalse(tk_runtime_safe())

    def test_windows_python_keeps_tk_runtime_available(self) -> None:
        with (
            patch("boogart.app.sys.platform", "win32"),
            patch("boogart.app.sys.executable", "C:/Users/USER/AppData/Local/Programs/Python/Python311/python.exe"),
            patch("boogart.app.sys.base_prefix", "C:/Users/USER/AppData/Local/Programs/Python/Python311"),
            patch("boogart.app.sys.version_info", (3, 11, 9)),
        ):
            self.assertTrue(tk_runtime_safe())

    def test_hundred_day_no_feed_simulation_limits_starvation_and_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.downloads.mkdir(parents=True)
            install_boogart("jay", paths)
            state = load_state(paths.state_file)
            start = datetime.fromisoformat(state.birth_time)
            events: list[str] = []

            for day in range(100):
                frame = run_heartbeat(paths, start + timedelta(days=day), RuntimeConfig(dev_fast=False))
                events.extend(frame.events)

            saved = load_state(paths.state_file)
            starvation_deaths = [event for event in events if event == "dead:starvation"]
            file_count = sum(1 for path in root.rglob("*") if path.is_file())
            self.assertLessEqual(len(starvation_deaths), 15)
            self.assertLess(file_count, 250)
            self.assertLess(saved.death_count, 15)

    def test_hundred_day_fed_simulation_has_no_starvation_deaths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.downloads.mkdir(parents=True)
            install_boogart("jay", paths)
            start = datetime.fromisoformat(load_state(paths.state_file).birth_time)
            events: list[str] = []

            for day in range(100):
                if day % 2 == 0:
                    (paths.downloads / f"day_{day:03d}.food").write_text("x", encoding="utf-8")
                frame = run_heartbeat(paths, start + timedelta(days=day), RuntimeConfig(dev_fast=False))
                events.extend(frame.events)

            saved = load_state(paths.state_file)
            file_count = sum(1 for path in root.rglob("*") if path.is_file())
            self.assertFalse(any(event == "dead:starvation" for event in events))
            self.assertEqual(saved.lifecycle, "alive")
            self.assertEqual(saved.death_count, 0)
            self.assertLess(file_count, 250)


class FakeSignal:
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback) -> None:
        self.callback = callback


class FakeWidget:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.clicked = FakeSignal()
        self.timeout = FakeSignal()
        self.text = ""
        self.plain_text = ""
        self.value = 0
        self.minimum = None
        self.maximum = None
        self.title = ""
        self.closed = False

    def setWindowTitle(self, value: str) -> None:
        self.title = value

    def windowFlags(self) -> int:
        return 0

    def setRange(self, minimum: int, maximum: int) -> None:
        self.minimum = minimum
        self.maximum = maximum

    def setValue(self, value: int) -> None:
        self.value = value

    def setText(self, value: str) -> None:
        self.text = value

    def setPlainText(self, value: str) -> None:
        self.plain_text = value

    def close(self) -> None:
        self.closed = True

    def size(self):
        return self

    def scaled(self, *args, **kwargs):
        return self

    def isNull(self) -> bool:
        return False

    def exec(self) -> int:
        return 0

    def __getattr__(self, _name):
        def method(*args, **kwargs):
            return None

        return method


class FakeApplication(FakeWidget):
    @classmethod
    def instance(cls):
        return None

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


class FakeQt:
    AlignCenter = 0
    WindowStaysOnTopHint = 1
    KeepAspectRatio = 0
    SmoothTransformation = 0
    AlignmentFlag = SimpleNamespace(AlignCenter=0)
    WindowType = SimpleNamespace(WindowStaysOnTopHint=1)
    AspectRatioMode = SimpleNamespace(KeepAspectRatio=0)
    TransformationMode = SimpleNamespace(SmoothTransformation=0)


class FakePixmap(FakeWidget):
    pass


def fake_qt_modules():
    core = SimpleNamespace(Qt=FakeQt, QTimer=FakeWidget)
    gui = SimpleNamespace(QPixmap=FakePixmap)
    widgets = SimpleNamespace(
        QApplication=FakeApplication,
        QWidget=FakeWidget,
        QLabel=FakeWidget,
        QProgressBar=FakeWidget,
        QTextEdit=FakeWidget,
        QPushButton=FakeWidget,
        QVBoxLayout=FakeWidget,
        QHBoxLayout=FakeWidget,
    )
    return core, gui, widgets


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
        lock_file=root / "Data" / "boogart.lock",
        tether_file=root / ".boogart_tether",
        debug_file=root / "Data" / "debug.txt",
        log_file=root / "Desktop" / "log.txt",
        desktop_boogart_png=root / "Desktop" / "boogart.png",
    )


if __name__ == "__main__":
    unittest.main()
