from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.lifecycle import (
    DeathCause,
    apply_death_rule_updates,
    can_rebirth,
    evaluate_death_rules,
    first_death_cause,
    kill_boogart,
    rebirth,
    rot_stage,
)
from boogart.core.state import BoogartState, corpse_records, state_from_dict
from boogart.world.observations import PlaceProfile


class LifecycleTests(unittest.TestCase):
    def test_death_leaves_body_and_metadata(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")

        with tempfile.TemporaryDirectory() as tmp:
            corpse = kill_boogart(state, Path(tmp), DeathCause("hazard", "unsafe"), now)

            self.assertFalse(corpse.exists())
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

    def test_death_rule_evaluation_is_pure_until_updates_are_applied(self) -> None:
        now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        place = PlaceProfile(Path("/tmp"), "tmp", 0, 0, 0, 0, 0)
        state = BoogartState.new("jay")
        state.hunger = 100

        evaluation = evaluate_death_rules(state, place, [], now)

        self.assertIsNone(evaluation.cause)
        self.assertNotIn("critical_hunger_since", state.memory)
        apply_death_rule_updates(state, evaluation)
        self.assertIn("critical_hunger_since", state.memory)

    def test_state_migration_adds_schema_and_typed_corpse_records(self) -> None:
        state = state_from_dict(
            {
                "username": "jay",
                "corpse_records": [
                    {
                        "cause": "hazard",
                        "death_time": "2026-01-01T00:00:00+00:00",
                        "folder_path": "/tmp",
                        "corpse_path": "/tmp/dead_boogart.png",
                    }
                ],
            }
        )

        self.assertEqual(state.schema_version, 2)
        self.assertEqual(corpse_records(state)[0].cause, "hazard")


if __name__ == "__main__":
    unittest.main()
