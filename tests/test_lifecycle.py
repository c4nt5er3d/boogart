from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.lifecycle import DeathCause, first_death_cause, can_rebirth, kill_boogart, rebirth, rot_stage
from boogart.core.state import BoogartState
from boogart.world.observations import PlaceProfile


class LifecycleTests(unittest.TestCase):
    def test_death_leaves_body_and_metadata(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")

        with tempfile.TemporaryDirectory() as tmp:
            corpse = kill_boogart(state, Path(tmp), DeathCause("hazard", "unsafe"), now)

            self.assertTrue(corpse.exists())
            self.assertEqual(state.lifecycle, "waiting_rebirth")
            self.assertEqual(state.death_cause, "hazard")
            self.assertEqual(len(state.corpse_records), 1)
            self.assertEqual(state.corpse_records[0]["rot_stage"], "fresh")

    def test_rot_stage_windows(self) -> None:
        death = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(timespec="seconds")

        self.assertEqual(rot_stage(death, datetime(2026, 1, 1, 6, tzinfo=timezone.utc)), "fresh")
        self.assertEqual(rot_stage(death, datetime(2026, 1, 2, tzinfo=timezone.utc)), "still")
        self.assertEqual(rot_stage(death, datetime(2026, 1, 4, tzinfo=timezone.utc)), "rotting")
        self.assertEqual(rot_stage(death, datetime(2026, 1, 7, tzinfo=timezone.utc)), "old")

    def test_rebirth_waits_thirty_minutes_and_preserves_history(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")

        with tempfile.TemporaryDirectory() as tmp:
            kill_boogart(state, Path(tmp), DeathCause("starvation", "hungry"), now)
            old_incarnation = state.incarnation_id

            self.assertFalse(can_rebirth(state, now + timedelta(minutes=29)))
            self.assertTrue(can_rebirth(state, now + timedelta(minutes=30)))

            rebirth(state, now + timedelta(minutes=30))

            self.assertEqual(state.lifecycle, "alive")
            self.assertEqual(state.stage, "newborn")
            self.assertNotEqual(state.incarnation_id, old_incarnation)
            self.assertEqual(len(state.corpse_records), 1)
            self.assertEqual(state.global_memory["rebirth_count"], 1)

    def test_poison_and_starvation_are_distinct_death_causes(self) -> None:
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        place = PlaceProfile(Path("/tmp"), "tmp", 0, 0, 0, 0, 0)

        poisoned = BoogartState.new("jay")
        poisoned.memory["last_food_eaten"] = "battery.food"
        self.assertEqual(first_death_cause(poisoned, place, [], now).id, "poison")

        starving = BoogartState.new("jay")
        starving.hunger = 100
        starving.memory["critical_hunger_since"] = (now - timedelta(hours=7)).isoformat(timespec="seconds")
        self.assertEqual(first_death_cause(starving, place, [], now).id, "starvation")


if __name__ == "__main__":
    unittest.main()
