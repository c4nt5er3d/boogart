from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FileObservation:
    path: Path
    name: str
    extension: str
    kind: str
    tags: frozenset[str]
    edible: bool = False
    hazard: bool = False
    corpse: bool = False
    boogart_owned: bool = False
    emotional_weight: int = 0


@dataclass(frozen=True)
class PlaceProfile:
    path: Path
    folder_name: str
    file_count: int
    folder_count: int
    food_count: int
    hazard_count: int
    corpse_count: int
    tags: frozenset[str] = field(default_factory=frozenset)

