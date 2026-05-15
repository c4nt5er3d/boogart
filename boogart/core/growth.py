from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class GrowthStage:
    id: str
    label: str
    phase: int
    starts_after: timedelta


STAGES: tuple[GrowthStage, ...] = (
    GrowthStage("kitten", "Kitten", 1, timedelta()),
    GrowthStage("cat", "Cat", 2, timedelta(days=3)),
    GrowthStage("shifting", "Shifting", 3, timedelta(days=14)),
    GrowthStage("wrong", "Wrong", 4, timedelta(days=30)),
    GrowthStage("final", "Final Form", 6, timedelta(days=60)),
)

STAGE_IDS = tuple(stage.id for stage in STAGES)
VOCALIZATION_ONLY_STAGES = {"kitten"}


def stage_for_age(age: timedelta) -> GrowthStage:
    current = STAGES[0]
    for stage in STAGES:
        if age >= stage.starts_after:
            current = stage
    return current


def stage_for_birth_time(birth_time: str, now: datetime | None = None, care_slowdown_days: int = 0) -> GrowthStage:
    current_time = now or datetime.now(timezone.utc)
    age = max(current_time - parse_timestamp(birth_time) - timedelta(days=care_slowdown_days), timedelta())
    return stage_for_age(age)


def stage_for_created_at(created_at: str, now: datetime | None = None) -> GrowthStage:
    return stage_for_birth_time(created_at, now)


def phase_for_birth_time(birth_time: str, now: datetime | None = None, care_slowdown_days: int = 0) -> int:
    return stage_for_birth_time(birth_time, now, care_slowdown_days).phase


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_stage(stage_id: str) -> GrowthStage:
    for stage in STAGES:
        if stage.id == stage_id:
            return stage
    raise ValueError(f"unknown growth stage: {stage_id}")
