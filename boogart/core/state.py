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
    phase: str
    hunger: int
    neglect: int
    affection: int
    created_at: str
    updated_at: str
    memory: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def new(cls, username: str) -> "BoogartState":
        now = utc_now()
        return cls(
            run_id=str(uuid4()),
            username=username.strip() or "friend",
            phase="kitten",
            hunger=20,
            neglect=0,
            affection=0,
            created_at=now,
            updated_at=now,
        )


def save_state(path: Path, state: BoogartState) -> None:
    path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
