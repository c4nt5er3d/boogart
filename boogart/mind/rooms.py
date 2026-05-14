from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from boogart.mind.context import BrainContext
from boogart.mind import tuning
from boogart.world.scanner import scan_folder


@dataclass(frozen=True)
class RoomScore:
    path: Path
    value: int
    reasons: tuple[str, ...] = field(default_factory=tuple)


def score_room(ctx: BrainContext, path: Path) -> RoomScore:
    place, observations = scan_folder(path, generated_files=ctx.state.generated_files, max_entries=80)
    visits = _room_visits(ctx).get(str(path), 0)
    value = 0
    reasons: list[str] = []

    if visits:
        bonus = min(30, visits * tuning.ROOM_FAMILIARITY_WEIGHT)
        value += bonus
        reasons.append(f"familiar +{bonus}")

    if "empty_room" in place.tags:
        value += tuning.ROOM_QUIET_WEIGHT
        reasons.append(f"quiet +{tuning.ROOM_QUIET_WEIGHT}")

    curious_tags = {"code_room", "picture_room", "paper_room", "music_room", "video_room"}
    if place.tags & curious_tags:
        value += tuning.ROOM_CURIOUS_TAG_WEIGHT
        reasons.append(f"interesting +{tuning.ROOM_CURIOUS_TAG_WEIGHT}")

    if any(item.edible for item in observations):
        value += tuning.ROOM_FOOD_MEMORY_WEIGHT
        reasons.append(f"food scent +{tuning.ROOM_FOOD_MEMORY_WEIGHT}")

    if any("gift" in item.tags for item in observations):
        value += tuning.ROOM_GIFT_WEIGHT
        reasons.append(f"gift memory +{tuning.ROOM_GIFT_WEIGHT}")

    if place.hazard_count:
        penalty = place.hazard_count * tuning.ROOM_HAZARD_PENALTY
        value -= penalty
        reasons.append(f"hazard -{penalty}")

    if place.corpse_count:
        penalty = place.corpse_count * tuning.ROOM_CORPSE_PENALTY
        value -= penalty
        reasons.append(f"corpse -{penalty}")

    if "exposed" in place.tags:
        value -= tuning.ROOM_EXPOSED_PENALTY
        reasons.append(f"exposed -{tuning.ROOM_EXPOSED_PENALTY}")

    fear = ctx.needs.get("fear", 0)
    curiosity = ctx.needs.get("curiosity", 0) + ctx.appraisal.pressure.get("curiosity", 0)
    if fear:
        value -= fear * tuning.ROOM_FEAR_PENALTY
        reasons.append(f"fear -{fear * tuning.ROOM_FEAR_PENALTY}")
    if curiosity:
        value += curiosity * tuning.ROOM_CURIOSITY_WEIGHT
        reasons.append(f"curiosity +{curiosity * tuning.ROOM_CURIOSITY_WEIGHT}")

    return RoomScore(path=path, value=value, reasons=tuple(reasons))


def choose_room(ctx: BrainContext, candidates: list[Path]) -> RoomScore | None:
    scored = [score_room(ctx, candidate) for candidate in candidates]
    if not scored:
        return None
    scored.sort(key=lambda room: (room.value, room.path.name.lower()), reverse=True)
    return scored[0]


def remember_room_visit(ctx: BrainContext, path: Path) -> None:
    visits = _room_visits(ctx)
    visits[str(path)] = int(visits.get(str(path), 0) or 0) + 1


def _room_visits(ctx: BrainContext) -> dict[str, int]:
    raw = ctx.state.memory.setdefault("room_visits", {})
    if not isinstance(raw, dict):
        raw = {}
        ctx.state.memory["room_visits"] = raw
    visits: dict[str, int] = {}
    for key, value in raw.items():
        visits[str(key)] = int(value or 0)
    ctx.state.memory["room_visits"] = visits
    return visits
