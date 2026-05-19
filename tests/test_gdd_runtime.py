from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from boogart.app import boogart_lock, install_boogart
from boogart.cleanup import cleanup
from boogart.core.debug import debug_status
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state, state_from_dict
from boogart.rendering.png import read_png_metadata
from boogart.rendering.sprite import render_boogart_sprite
from boogart.runtime import HeartbeatFrame, RuntimeConfig, artifact_metadata, body_metadata, movement_candidates, run_heartbeat, run_simulation
from boogart.ui.terminal import render_live_panel


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
            self.assertIn("16:01", panel)
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

    def test_metadata_missing_current_body_can_be_recovered_by_hash(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = make_paths(root)
            paths.desktop.mkdir(parents=True)
            paths.data_dir.mkdir()
            state = BoogartState.new("jay")
            state.current_folder = str(paths.desktop)
            state.body_name = "boogart.png"
            state.next_move_at = (now + timedelta(hours=1)).isoformat(timespec="seconds")
            legacy_body = paths.downloads / "boogart.png"
            paths.downloads.mkdir()
            legacy_body.write_text("legacy body", encoding="utf-8")
            state.body_hash = __import__("hashlib").sha256(b"legacy body").hexdigest()
            save_state(paths.state_file, state)

            frame = run_heartbeat(paths, now)
            saved = load_state(paths.state_file)

            self.assertEqual(frame.body_path, legacy_body)
            self.assertEqual(Path(saved.current_folder), paths.downloads)

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
