from __future__ import annotations

import random
from datetime import date
from pathlib import Path


HAZARD_MARKERS = ("slipperyfloor.hazard", "badwire.hazard", "coldspot.hazard", "sharpcorner.hazard")


def daily_hazard_name(day: date, seed: str) -> str:
    rng = random.Random(f"{seed}:{day.isoformat()}")
    return rng.choice(HAZARD_MARKERS)


def create_daily_hazard(folder: Path, day: date, seed: str) -> Path:
    path = folder / daily_hazard_name(day, seed)
    if not path.exists():
        path.write_text("unsafe for boogart\n", encoding="utf-8")
    return path
