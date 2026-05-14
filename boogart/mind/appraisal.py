from __future__ import annotations

from dataclasses import dataclass, field

from boogart.world.observations import FileObservation, PlaceProfile


@dataclass(frozen=True)
class AppraisalResult:
    pressure: dict[str, int] = field(default_factory=dict)
    subjects: tuple[str, ...] = ()
    tags: frozenset[str] = field(default_factory=frozenset)


def appraise(place: PlaceProfile, observations: list[FileObservation]) -> AppraisalResult:
    pressure = {
        "hunger": 0,
        "fear": 0,
        "loneliness": 0,
        "curiosity": 0,
        "affection": 0,
        "corruption": 0,
    }
    subjects: list[str] = []
    tags: set[str] = set(place.tags)

    if "empty_room" in place.tags:
        pressure["loneliness"] += 3
    if "busy" in place.tags:
        pressure["curiosity"] += 2
    if "code_room" in place.tags or "picture_room" in place.tags or "paper_room" in place.tags:
        pressure["curiosity"] += 4

    for item in observations:
        tags.update(item.tags)
        if item.edible:
            pressure["hunger"] += 3
            pressure["affection"] += 1
            subjects.append(item.name)
        if item.hazard:
            pressure["fear"] += 7
            subjects.append(item.name)
        if item.corpse:
            pressure["fear"] += 9
            pressure["corruption"] += 3
            subjects.append(item.name)
        if "repeated_final" in item.tags:
            pressure["curiosity"] += 2
            pressure["corruption"] += 1
            subjects.append(item.name)
        if "project" in item.tags or "code" in item.tags:
            pressure["curiosity"] += 1

    return AppraisalResult(pressure=pressure, subjects=tuple(subjects[:5]), tags=frozenset(tags))
