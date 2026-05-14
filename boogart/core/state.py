from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class CorpseRecord:
    id: str
    incarnation_id: str
    cause: str
    reason: str
    death_time: str
    folder_path: str
    corpse_path: str
    rot_stage: str = "fresh"
    seen: bool = False
    eaten: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CorpseRecord":
        return cls(
            id=str(data.get("id") or uuid4()),
            incarnation_id=str(data.get("incarnation_id") or ""),
            cause=str(data.get("cause") or "unknown"),
            reason=str(data.get("reason") or ""),
            death_time=str(data.get("death_time") or utc_now()),
            folder_path=str(data.get("folder_path") or ""),
            corpse_path=str(data.get("corpse_path") or ""),
            rot_stage=str(data.get("rot_stage") or "fresh"),
            seen=bool(data.get("seen", False)),
            eaten=bool(data.get("eaten", False)),
        )


@dataclass
class NeedsMemory:
    fear: int = 0
    curiosity: int = 0
    loneliness: int = 0
    trust: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "NeedsMemory":
        return cls(
            fear=int(data.get("fear") or 0),
            curiosity=int(data.get("curiosity") or 0),
            loneliness=int(data.get("loneliness") or 0),
            trust=int(data.get("trust") or 0),
        )


@dataclass
class MessageRecord:
    text: str
    at: str

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "MessageRecord":
        return cls(text=str(data.get("text") or ""), at=str(data.get("at") or utc_now()))


@dataclass
class MessageMemory:
    cooldowns: dict[str, object] = field(default_factory=dict)
    recent: list[MessageRecord] = field(default_factory=list)

    @classmethod
    def from_memory_dict(cls, memory: dict[str, object]) -> "MessageMemory":
        recent = [
            MessageRecord.from_dict(item)
            for item in _list(memory.get("recent_messages"))
            if isinstance(item, dict)
        ]
        return cls(cooldowns=_dict(memory.get("message_cooldowns")), recent=recent)


@dataclass
class BoogartState:
    schema_version: int
    run_id: str
    username: str
    stage: str
    lifecycle: str
    incarnation_id: str
    current_folder: str
    wander_scope: str
    hunger: int
    neglect: int
    affection: int
    corruption: int
    created_at: str
    birth_at: str
    updated_at: str
    died_at: str | None = None
    death_cause: str | None = None
    rebirth_available_at: str | None = None
    corpse_records: list[dict[str, object]] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    global_memory: dict[str, object] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)

    @classmethod
    def new(cls, username: str) -> "BoogartState":
        now = utc_now()
        return cls(
            schema_version=SCHEMA_VERSION,
            run_id=str(uuid4()),
            username=username.strip() or "friend",
            stage="newborn",
            lifecycle="alive",
            incarnation_id=str(uuid4()),
            current_folder="",
            wander_scope="desktop",
            hunger=20,
            neglect=0,
            affection=0,
            corruption=0,
            created_at=now,
            birth_at=now,
            updated_at=now,
        )


def save_state(path: Path, state: BoogartState) -> None:
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def load_state(path: Path) -> BoogartState:
    data = json.loads(path.read_text(encoding="utf-8"))
    return state_from_dict(data)


def state_from_dict(data: dict[str, object]) -> BoogartState:
    data = migrate_state_dict(data)
    now = utc_now()
    run_id = str(data.get("run_id") or uuid4())
    username = str(data.get("username") or "friend")
    birth_at = str(data.get("birth_at") or data.get("created_at") or now)

    return BoogartState(
        schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        run_id=run_id,
        username=username,
        stage=str(data.get("stage") or "newborn"),
        lifecycle=str(data.get("lifecycle") or "alive"),
        incarnation_id=str(data.get("incarnation_id") or uuid4()),
        current_folder=str(data.get("current_folder") or ""),
        wander_scope=str(data.get("wander_scope") or "desktop"),
        hunger=int(data.get("hunger") or 0),
        neglect=int(data.get("neglect") or 0),
        affection=int(data.get("affection") or 0),
        corruption=int(data.get("corruption") or 0),
        created_at=str(data.get("created_at") or now),
        birth_at=birth_at,
        updated_at=str(data.get("updated_at") or now),
        died_at=_optional_str(data.get("died_at")),
        death_cause=_optional_str(data.get("death_cause")),
        rebirth_available_at=_optional_str(data.get("rebirth_available_at")),
        corpse_records=[asdict(CorpseRecord.from_dict(item)) for item in _list_of_dicts(data.get("corpse_records"))],
        generated_files=[str(item) for item in _list(data.get("generated_files"))],
        global_memory=_dict(data.get("global_memory")),
        memory=_dict(data.get("memory")),
    )


def migrate_state_dict(data: dict[str, object]) -> dict[str, object]:
    migrated = dict(data)
    if "schema_version" not in migrated:
        migrated["schema_version"] = 1
    if "birth_at" not in migrated:
        migrated["birth_at"] = migrated.get("created_at") or utc_now()
    if "wander_scope" not in migrated:
        migrated["wander_scope"] = "desktop"
    migrated["schema_version"] = SCHEMA_VERSION
    return migrated


def corpse_records(state: BoogartState) -> list[CorpseRecord]:
    return [CorpseRecord.from_dict(item) for item in state.corpse_records]


def set_corpse_records(state: BoogartState, records: list[CorpseRecord]) -> None:
    state.corpse_records = [asdict(record) for record in records]


def message_memory(state: BoogartState) -> MessageMemory:
    return MessageMemory.from_memory_dict(state.memory)


def needs_memory(state: BoogartState) -> NeedsMemory:
    raw = state.memory.get("needs")
    if not isinstance(raw, dict):
        return NeedsMemory()
    return NeedsMemory.from_dict(raw)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    return [item for item in _list(value) if isinstance(item, dict)]
