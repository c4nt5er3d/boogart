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
