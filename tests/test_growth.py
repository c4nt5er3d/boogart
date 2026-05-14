from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from boogart.core.growth import STAGES, stage_for_created_at
from boogart.core.state import BoogartState


class GrowthTests(unittest.TestCase):
    def test_stage_boundaries_cover_seven_day_arc(self) -> None:
        now = datetime(2026, 1, 8, tzinfo=timezone.utc)
        cases = [
            (timedelta(hours=0), "newborn"),
            (timedelta(hours=12), "baby_kitten"),
            (timedelta(days=1), "kitten"),
            (timedelta(days=2), "young_cat"),
            (timedelta(days=3), "cat"),
            (timedelta(days=4), "first_shift"),
            (timedelta(days=5), "changed"),
            (timedelta(days=6), "final"),
            (timedelta(days=7), "final"),
        ]

        for age, expected in cases:
            created_at = (now - age).isoformat(timespec="seconds")
            with self.subTest(age=age):
                self.assertEqual(stage_for_created_at(created_at, now).id, expected)

    def test_new_state_starts_newborn(self) -> None:
        state = BoogartState.new("jay")
        self.assertEqual(state.stage, "newborn")

    def test_all_stage_ids_are_unique(self) -> None:
        ids = [stage.id for stage in STAGES]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
