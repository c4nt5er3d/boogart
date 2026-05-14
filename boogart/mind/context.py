from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from boogart.core.state import BoogartState
from boogart.world.observations import FileObservation, PlaceProfile


@dataclass
class BrainContext:
    state: BoogartState
    folder: Path
    place: PlaceProfile
    observations: list[FileObservation]
    now: datetime


@dataclass(frozen=True)
class BrainResult:
    action_id: str
    message: str = ""
    path: Path | None = None
