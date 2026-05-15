from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BoogartState:
    schema_version: int
    username: str
    boogart_id: str
    generation: int
    birth_time: str
    phase: int
    lineage: list[str]
    parent_id: str | None
    death_count: int
    copy_count: int
    body_hash: str
    body_name: str
    current_folder: str
    lifecycle: str
    hunger: int
    neglect: int
    affection: int
    created_at: str
    updated_at: str
    last_active_at: str
    next_move_at: str
    next_hunger_at: str
    next_txt_at: str
    last_log_day: str
    log_count_today: int
    txt_count_today: int
    addressed_username: bool
    generated_files: list[str] = field(default_factory=list)
    manifest: list[str] = field(default_factory=list)
    favorites: dict[str, int] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)

    @classmethod
    def new(cls, username: str) -> "BoogartState":
        now = utc_now()
        boogart_id = str(uuid4())
        return cls(
            schema_version=SCHEMA_VERSION,
            username=username.strip() or "friend",
            boogart_id=boogart_id,
            generation=1,
            birth_time=now,
            phase=1,
            lineage=[boogart_id],
            parent_id=None,
            death_count=0,
            copy_count=0,
            body_hash="",
            body_name="boogart.png",
            current_folder="",
            lifecycle="alive",
            hunger=18,
            neglect=0,
            affection=0,
            created_at=now,
            updated_at=now,
            last_active_at=now,
            next_move_at=now,
            next_hunger_at=now,
            next_txt_at=now,
            last_log_day="",
            log_count_today=0,
            txt_count_today=0,
            addressed_username=False,
        )


def save_state(path: Path, state: BoogartState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(state), indent=2, sort_keys=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def load_state(path: Path) -> BoogartState:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return state_from_dict(data)


def state_from_dict(data: dict[str, object]) -> BoogartState:
    migrated = migrate_state_dict(data)
    state = BoogartState.new(str(migrated.get("username") or "friend"))

    for field_name in state.__dataclass_fields__:
        if field_name in migrated:
            setattr(state, field_name, migrated[field_name])

    state.schema_version = SCHEMA_VERSION
    state.phase = max(1, min(6, _phase_value(state.phase)))
    state.generation = max(1, int(state.generation or 1))
    state.death_count = max(0, int(state.death_count or 0))
    state.copy_count = max(0, int(state.copy_count or 0))
    state.hunger = max(0, min(100, int(state.hunger or 0)))
    state.neglect = max(0, int(state.neglect or 0))
    state.affection = max(0, int(state.affection or 0))
    state.log_count_today = max(0, int(state.log_count_today or 0))
    state.txt_count_today = max(0, int(state.txt_count_today or 0))
    state.lineage = [str(item) for item in _list(state.lineage)] or [state.boogart_id]
    state.generated_files = [str(item) for item in _list(state.generated_files)]
    state.manifest = [str(item) for item in _list(state.manifest)]
    state.favorites = {str(key): int(value) for key, value in _dict(state.favorites).items() if isinstance(value, int)}
    state.memory = _dict(state.memory)
    return state


def migrate_state_dict(data: dict[str, object]) -> dict[str, object]:
    now = utc_now()
    migrated = dict(data)
    migrated["schema_version"] = SCHEMA_VERSION
    if "boogart_id" not in migrated:
        migrated["boogart_id"] = str(migrated.get("incarnation_id") or migrated.get("run_id") or uuid4())
    if "birth_time" not in migrated:
        migrated["birth_time"] = str(migrated.get("birth_at") or migrated.get("created_at") or now)
    if "phase" not in migrated:
        migrated["phase"] = _phase_from_legacy_stage(str(migrated.get("stage") or ""))
    if "generation" not in migrated:
        migrated["generation"] = 1
    if "lineage" not in migrated:
        migrated["lineage"] = [str(migrated["boogart_id"])]
    if "death_count" not in migrated:
        migrated["death_count"] = int(_dict(migrated.get("global_memory")).get("death_count") or 0)
    if "body_name" not in migrated:
        migrated["body_name"] = "boogart.png"
    if "lifecycle" not in migrated:
        migrated["lifecycle"] = "alive"
    if "current_folder" not in migrated:
        migrated["current_folder"] = ""
    if "last_active_at" not in migrated:
        migrated["last_active_at"] = str(migrated.get("updated_at") or now)
    for key in ("created_at", "updated_at", "next_move_at", "next_hunger_at", "next_txt_at"):
        migrated.setdefault(key, now)
    migrated.setdefault("last_log_day", "")
    migrated.setdefault("log_count_today", 0)
    migrated.setdefault("txt_count_today", 0)
    migrated.setdefault("copy_count", 0)
    migrated.setdefault("body_hash", "")
    migrated.setdefault("manifest", migrated.get("generated_files") or [])
    migrated.setdefault("favorites", {})
    migrated.setdefault("memory", {})
    migrated.setdefault("addressed_username", False)
    return migrated


def remember_generated_file(state: BoogartState, path: Path) -> None:
    value = str(path)
    if value not in state.generated_files:
        state.generated_files.append(value)
    if value not in state.manifest:
        state.manifest.append(value)


def corpse_records(state: BoogartState) -> list[object]:
    return []


def set_corpse_records(state: BoogartState, records: list[object]) -> None:
    state.memory["legacy_corpse_records"] = []


def _phase_from_legacy_stage(stage: str) -> int:
    stages = {
        "newborn": 1,
        "baby_kitten": 1,
        "kitten": 1,
        "young_cat": 2,
        "cat": 2,
        "first_shift": 3,
        "changed": 4,
        "final": 6,
    }
    return stages.get(stage, 1)


def _phase_value(value: object) -> int:
    try:
        return int(value or 1)
    except (TypeError, ValueError):
        return _phase_from_legacy_stage(str(value or ""))


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
