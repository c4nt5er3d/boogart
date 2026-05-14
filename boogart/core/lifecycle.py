from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from boogart.core.growth import parse_timestamp
from boogart.core.state import BoogartState
from boogart.world.observations import FileObservation, PlaceProfile


REBIRTH_DELAY = timedelta(minutes=30)


@dataclass(frozen=True)
class DeathCause:
    id: str
    reason: str


@dataclass(frozen=True)
class DeathRuleEvaluation:
    cause: DeathCause | None = None
    memory_updates: dict[str, object] | None = None
    memory_deletes: tuple[str, ...] = ()


class DeathRule:
    id = "death"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        raise NotImplementedError


class StarvationRule(DeathRule):
    id = "starvation"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        critical_since = state.memory.get("critical_hunger_since")
        if state.hunger < 100:
            return DeathRuleEvaluation(memory_deletes=("critical_hunger_since",))

        if not critical_since:
            return DeathRuleEvaluation(memory_updates={"critical_hunger_since": now.isoformat(timespec="seconds")})

        if now - parse_timestamp(str(critical_since)) >= timedelta(hours=6):
            return DeathRuleEvaluation(cause=DeathCause("starvation", "hunger stayed critical too long"))
        return DeathRuleEvaluation()


class PoisonFoodRule(DeathRule):
    id = "poison"
    poison_words = {"battery", "glass", "wire", "poison", "dead_boogart", "rot"}

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        eaten = str(state.memory.get("last_food_eaten", "")).lower()
        if eaten and any(word in eaten for word in self.poison_words):
            return DeathRuleEvaluation(cause=DeathCause("poison", f"bad food: {eaten}"))
        return DeathRuleEvaluation()


class HazardRule(DeathRule):
    id = "hazard"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        if place.hazard_count and state.hunger >= 70:
            return DeathRuleEvaluation(cause=DeathCause("hazard", "injured in an unsafe folder while weak"))
        return DeathRuleEvaluation()


class NeglectRule(DeathRule):
    id = "neglect"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        if state.neglect >= 7 and state.hunger >= 80:
            return DeathRuleEvaluation(cause=DeathCause("neglect", "neglect and hunger collapsed together"))
        return DeathRuleEvaluation()


class CorpseShockRule(DeathRule):
    id = "corpse_shock"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        if place.corpse_count and state.stage in {"newborn", "baby_kitten"} and state.neglect >= 3:
            return DeathRuleEvaluation(cause=DeathCause("corpse_shock", "too fragile to understand the body"))
        return DeathRuleEvaluation()


class RotExposureRule(DeathRule):
    id = "rot_exposure"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        for corpse in state.corpse_records:
            if corpse.get("eaten"):
                continue
            if corpse.get("folder_path") == str(place.path) and rot_stage(str(corpse.get("death_time")), now) in {"rotting", "old"}:
                if state.hunger >= 70 or state.corruption >= 40:
                    return DeathRuleEvaluation(cause=DeathCause("rot_exposure", "stayed too close to an old body"))
        return DeathRuleEvaluation()


class LateStageFailureRule(DeathRule):
    id = "late_stage_failure"

    def evaluate(self, state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime) -> DeathRuleEvaluation:
        if state.stage in {"changed", "final"} and state.neglect >= 9 and state.corruption >= 80:
            return DeathRuleEvaluation(cause=DeathCause("late_stage_failure", "the final form could not hold"))
        return DeathRuleEvaluation()


DEATH_RULES: tuple[DeathRule, ...] = (
    PoisonFoodRule(),
    StarvationRule(),
    HazardRule(),
    NeglectRule(),
    CorpseShockRule(),
    RotExposureRule(),
    LateStageFailureRule(),
)


def first_death_cause(state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime | None = None) -> DeathCause | None:
    return evaluate_death_rules(state, place, observations, now).cause


def evaluate_death_rules(state: BoogartState, place: PlaceProfile, observations: list[FileObservation], now: datetime | None = None) -> DeathRuleEvaluation:
    current_time = now or datetime.now(timezone.utc)
    merged_updates: dict[str, object] = {}
    merged_deletes: list[str] = []
    for rule in DEATH_RULES:
        evaluation = rule.evaluate(state, place, observations, current_time)
        if evaluation.memory_updates:
            merged_updates.update(evaluation.memory_updates)
        merged_deletes.extend(evaluation.memory_deletes)
        if evaluation.cause:
            return DeathRuleEvaluation(evaluation.cause, merged_updates or None, tuple(merged_deletes))
    return DeathRuleEvaluation(memory_updates=merged_updates or None, memory_deletes=tuple(merged_deletes))


def apply_death_rule_updates(state: BoogartState, evaluation: DeathRuleEvaluation) -> None:
    for key in evaluation.memory_deletes:
        state.memory.pop(key, None)
    if evaluation.memory_updates:
        state.memory.update(evaluation.memory_updates)


def kill_boogart(state: BoogartState, folder: Path, cause: DeathCause, now: datetime | None = None) -> Path:
    current_time = now or datetime.now(timezone.utc)
    death_time = current_time.isoformat(timespec="seconds")
    corpse_path = folder / "dead_boogart.png"

    state.lifecycle = "waiting_rebirth"
    state.died_at = death_time
    state.death_cause = cause.id
    state.rebirth_available_at = (current_time + REBIRTH_DELAY).isoformat(timespec="seconds")
    state.global_memory["death_count"] = int(state.global_memory.get("death_count", 0)) + 1
    state.corpse_records.append(
        {
            "id": str(uuid4()),
            "incarnation_id": state.incarnation_id,
            "cause": cause.id,
            "reason": cause.reason,
            "death_time": death_time,
            "folder_path": str(folder),
            "corpse_path": str(corpse_path),
            "rot_stage": "fresh",
            "seen": False,
            "eaten": False,
        }
    )
    track_generated_file(state, corpse_path)
    return corpse_path


def can_rebirth(state: BoogartState, now: datetime | None = None) -> bool:
    if state.lifecycle != "waiting_rebirth" or not state.rebirth_available_at:
        return False
    current_time = now or datetime.now(timezone.utc)
    return current_time >= parse_timestamp(state.rebirth_available_at)


def rebirth(state: BoogartState, now: datetime | None = None) -> None:
    current_time = now or datetime.now(timezone.utc)
    birth_time = current_time.isoformat(timespec="seconds")
    state.lifecycle = "alive"
    state.incarnation_id = str(uuid4())
    state.stage = "newborn"
    state.hunger = 20
    state.neglect = 0
    state.affection = max(0, state.affection // 2)
    state.birth_at = birth_time
    state.updated_at = birth_time
    state.died_at = None
    state.death_cause = None
    state.rebirth_available_at = None
    state.memory = {"reborn": True}
    state.global_memory["rebirth_count"] = int(state.global_memory.get("rebirth_count", 0)) + 1


def rot_stage(death_time: str, now: datetime | None = None) -> str:
    current_time = now or datetime.now(timezone.utc)
    age = current_time - parse_timestamp(death_time)
    if age < timedelta(hours=12):
        return "fresh"
    if age < timedelta(days=2):
        return "still"
    if age < timedelta(days=5):
        return "rotting"
    return "old"


def refresh_corpse_rot(state: BoogartState, now: datetime | None = None) -> None:
    for corpse in state.corpse_records:
        corpse["rot_stage"] = rot_stage(str(corpse.get("death_time")), now)


def track_generated_file(state: BoogartState, path: Path) -> None:
    value = str(path)
    if value not in state.generated_files:
        state.generated_files.append(value)
