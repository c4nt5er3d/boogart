from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class GrowthStage:
    id: str
    label: str
    starts_after: timedelta
    voice: str


STAGES: tuple[GrowthStage, ...] = (
    GrowthStage("newborn", "Newborn / Arrival", timedelta(hours=0), "vocalization"),
    GrowthStage("baby_kitten", "Baby Kitten", timedelta(hours=12), "vocalization"),
    GrowthStage("kitten", "Kitten", timedelta(days=1), "dialogue"),
    GrowthStage("young_cat", "Young Cat", timedelta(days=2), "dialogue"),
    GrowthStage("cat", "Cat", timedelta(days=3), "dialogue"),
    GrowthStage("first_shift", "First Shift", timedelta(days=4), "dialogue"),
    GrowthStage("changed", "Changed", timedelta(days=5), "dialogue"),
    GrowthStage("final", "Final Form", timedelta(days=6), "dialogue"),
)

STAGE_IDS = tuple(stage.id for stage in STAGES)
VOCALIZATION_ONLY_STAGES = {"newborn", "baby_kitten"}


def stage_for_age(age: timedelta) -> GrowthStage:
    current = STAGES[0]
    for stage in STAGES:
        if age >= stage.starts_after:
            current = stage
        else:
            break
    return current


def stage_for_created_at(created_at: str, now: datetime | None = None) -> GrowthStage:
    created = parse_timestamp(created_at)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    return stage_for_age(max(current_time - created, timedelta()))


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_stage(stage_id: str) -> GrowthStage:
    for stage in STAGES:
        if stage.id == stage_id:
            return stage
    raise ValueError(f"unknown growth stage: {stage_id}")
