from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.state import BoogartState
from boogart.mind.appraisal import appraise
from boogart.mind.needs import apply_need_drift
from boogart.world.scanner import scan_folder


class AppraisalNeedsTests(unittest.TestCase):
    def test_appraisal_reads_symbolic_pressure_from_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "fish.food").write_text("", encoding="utf-8")
            (folder / "dead_boogart.png").write_text("", encoding="utf-8")
            (folder / "notes_final_FINAL.txt").write_text("", encoding="utf-8")

            place, observations = scan_folder(folder)
            result = appraise(place, observations)

            self.assertGreaterEqual(result.pressure["hunger"], 3)
            self.assertGreaterEqual(result.pressure["fear"], 9)
            self.assertGreaterEqual(result.pressure["corruption"], 4)
            self.assertIn("dead_boogart.png", result.subjects)

    def test_need_drift_updates_structured_memory(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = BoogartState.new("jay")
        state.updated_at = (now - timedelta(hours=2)).isoformat(timespec="seconds")

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "slipperyfloor.hazard").write_text("", encoding="utf-8")
            place, observations = scan_folder(folder)

            apply_need_drift(state, appraise(place, observations), now)

            self.assertGreaterEqual(state.hunger, 24)
            self.assertGreaterEqual(state.memory["needs"]["fear"], 7)


if __name__ == "__main__":
    unittest.main()
