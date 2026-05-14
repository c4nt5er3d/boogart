from __future__ import annotations

from dataclasses import dataclass

from boogart.core.state import BoogartState
from boogart.world.observations import FileObservation, PlaceProfile


@dataclass(frozen=True)
class FolderSnapshot:
    folder_path: str
    file_names: tuple[str, ...]
    folder_tags: tuple[str, ...]
    food_count: int
    hazard_count: int
    corpse_count: int


def snapshot_folder(place: PlaceProfile, observations: list[FileObservation]) -> FolderSnapshot:
    return FolderSnapshot(
        folder_path=str(place.path),
        file_names=tuple(sorted(item.name for item in observations)),
        folder_tags=tuple(sorted(place.tags)),
        food_count=place.food_count,
        hazard_count=place.hazard_count,
        corpse_count=place.corpse_count,
    )


def update_watcher_memory(state: BoogartState, snapshot: FolderSnapshot) -> list[str]:
    snapshots = state.global_memory.setdefault("folder_snapshots", {})
    if not isinstance(snapshots, dict):
        snapshots = {}
        state.global_memory["folder_snapshots"] = snapshots

    previous = snapshots.get(snapshot.folder_path)
    snapshots[snapshot.folder_path] = snapshot_to_dict(snapshot)

    if not isinstance(previous, dict):
        return first_visit_comments(snapshot)

    return compare_snapshots(dict_to_snapshot(previous), snapshot)


def first_visit_comments(snapshot: FolderSnapshot) -> list[str]:
    comments: list[str] = []
    if "empty_room" in snapshot.folder_tags:
        comments.append("this room has almost no edges.")
    elif "busy" in snapshot.folder_tags:
        comments.append("this room has too many little names.")
    elif "picture_room" in snapshot.folder_tags:
        comments.append("the pictures make this place crowded.")
    elif "code_room" in snapshot.folder_tags:
        comments.append("you make little machines here.")
    elif "paper_room" in snapshot.folder_tags:
        comments.append("this room has a lot of folded thoughts.")
    return comments


def compare_snapshots(previous: FolderSnapshot, current: FolderSnapshot) -> list[str]:
    comments: list[str] = []
    old_names = set(previous.file_names)
    new_names = set(current.file_names)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)

    if len(current.file_names) > len(previous.file_names) + 3:
        comments.append("this room was smaller before.")
    elif len(current.file_names) + 3 < len(previous.file_names):
        comments.append("this room lost some of its names.")

    if added:
        comments.append(comment_for_added(added[0]))
    if removed:
        comments.append(comment_for_removed(removed[0]))
    if current.food_count > previous.food_count:
        comments.append("something edible appeared.")
    if current.hazard_count > previous.hazard_count:
        comments.append("the floor learned a bad word.")
    if current.corpse_count > previous.corpse_count:
        comments.append("there is a body in the room now.")

    return comments[:3]


def time_aware_comments(state: BoogartState, hour: int) -> list[str]:
    if hour < 3 or hour >= 4:
        return []
    key = "last_hidden_hour_day"
    today = state.updated_at[:10]
    if state.memory.get(key) == today:
        return []
    state.memory[key] = today
    state.corruption = min(100, state.corruption + 1)
    return ["i was awake during the quiet hour."]


def comment_for_added(name: str) -> str:
    if name.lower().endswith(".food"):
        return "you left a small hunger shape."
    if "final" in name.lower():
        return "another ending appeared."
    return f"{name} is new here."


def comment_for_removed(name: str) -> str:
    if name == "dead_boogart.png":
        return "the body is missing."
    return f"{name} went somewhere else."


def snapshot_to_dict(snapshot: FolderSnapshot) -> dict[str, object]:
    return {
        "folder_path": snapshot.folder_path,
        "file_names": list(snapshot.file_names),
        "folder_tags": list(snapshot.folder_tags),
        "food_count": snapshot.food_count,
        "hazard_count": snapshot.hazard_count,
        "corpse_count": snapshot.corpse_count,
    }


def dict_to_snapshot(data: dict[str, object]) -> FolderSnapshot:
    return FolderSnapshot(
        folder_path=str(data.get("folder_path") or ""),
        file_names=tuple(str(item) for item in _list(data.get("file_names"))),
        folder_tags=tuple(str(item) for item in _list(data.get("folder_tags"))),
        food_count=int(data.get("food_count") or 0),
        hazard_count=int(data.get("hazard_count") or 0),
        corpse_count=int(data.get("corpse_count") or 0),
    )


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
