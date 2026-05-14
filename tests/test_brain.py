from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.lifecycle import DeathCause, kill_boogart
from boogart.core.state import BoogartState
from boogart.mind.brain import tick_state


class BrainTests(unittest.TestCase):
    def test_baby_vocalizes_when_nothing_else_matters(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")

        with tempfile.TemporaryDirectory() as tmp:
            result = tick_state(state, Path(tmp), now)

            self.assertEqual(result.action_id, "vocalize")

    def test_food_is_eaten_and_removed(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        state.hunger = 80

        with tempfile.TemporaryDirectory() as tmp:
            food = Path(tmp) / "fish.food"
            food.write_text("", encoding="utf-8")
            result = tick_state(state, Path(tmp), now)

            self.assertEqual(result.action_id, "eat_food")
            self.assertFalse(food.exists())
            self.assertEqual(state.memory["last_food_eaten"], "fish.food")

    def test_hazard_can_kill_when_boogs_is_weak(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        state.hunger = 70

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "slipperyfloor.hazard").write_text("", encoding="utf-8")
            result = tick_state(state, Path(tmp), now)

            self.assertEqual(result.action_id, "die")
            self.assertEqual(state.death_cause, "hazard")
            self.assertTrue((Path(tmp) / "dead_boogart.png").exists())

    def test_gift_is_given_after_hazard_seed_for_today(self) -> None:
        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        state.birth_at = (now - timedelta(days=2)).isoformat(timespec="seconds")
        state.stage = "young_cat"
        state.affection = 2
        state.memory["last_hazard_day"] = now.date().isoformat()

        with tempfile.TemporaryDirectory() as tmp:
            result = tick_state(state, Path(tmp), now)

            self.assertEqual(result.action_id, "give_gift")
            self.assertIsNotNone(result.path)
            self.assertTrue(result.path.exists())
            self.assertIn(str(result.path), state.generated_files)

    def test_daily_hazard_marker_can_be_seeded(self) -> None:
        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        state.birth_at = (now - timedelta(days=2)).isoformat(timespec="seconds")
        state.stage = "young_cat"

        with tempfile.TemporaryDirectory() as tmp:
            result = tick_state(state, Path(tmp), now)

            self.assertEqual(result.action_id, "seed_daily_hazard")
            self.assertEqual(result.path.suffix, ".hazard")
            self.assertTrue(result.path.exists())
            self.assertIn(str(result.path), state.generated_files)

    def test_rebirth_action_resets_growth_clock(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")

        with tempfile.TemporaryDirectory() as tmp:
            kill_boogart(state, Path(tmp), DeathCause("starvation", "hungry"), now)
            result = tick_state(state, Path(tmp), now + timedelta(minutes=30))

            self.assertEqual(result.action_id, "rebirth")
            self.assertEqual(state.lifecycle, "alive")
            self.assertEqual(state.stage, "newborn")

    def test_corrupted_hungry_boogart_can_eat_corpse_without_food(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        state.stage = "final"
        state.hunger = 100
        state.corruption = 50

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            kill_boogart(state, folder, DeathCause("hazard", "unsafe"), now - timedelta(days=1))
            state.lifecycle = "alive"
            state.hunger = 100
            state.corruption = 50
            result = tick_state(state, folder, now)

            self.assertEqual(result.action_id, "eat_corpse")
            self.assertTrue(state.corpse_records[0]["eaten"])
            self.assertTrue((folder / "stain_boogart.png").exists())


if __name__ == "__main__":
    unittest.main()
