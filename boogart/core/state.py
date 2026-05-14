from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class BoogartState:
    run_id: str
    username: str
    stage: str
    lifecycle: str
    incarnation_id: str
    current_folder: str
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
            run_id=str(uuid4()),
            username=username.strip() or "friend",
            stage="newborn",
            lifecycle="alive",
            incarnation_id=str(uuid4()),
            current_folder="",
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
    now = utc_now()
    run_id = str(data.get("run_id") or uuid4())
    username = str(data.get("username") or "friend")
    birth_at = str(data.get("birth_at") or data.get("created_at") or now)

    return BoogartState(
        run_id=run_id,
        username=username,
        stage=str(data.get("stage") or "newborn"),
        lifecycle=str(data.get("lifecycle") or "alive"),
        incarnation_id=str(data.get("incarnation_id") or uuid4()),
        current_folder=str(data.get("current_folder") or ""),
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
        corpse_records=_list_of_dicts(data.get("corpse_records")),
        generated_files=[str(item) for item in _list(data.get("generated_files"))],
        global_memory=_dict(data.get("global_memory")),
        memory=_dict(data.get("memory")),
    )


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
