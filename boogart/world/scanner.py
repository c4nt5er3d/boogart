from __future__ import annotations

from pathlib import Path

from boogart.world.classifiers import classify_path
from boogart.world.observations import FileObservation, PlaceProfile


def scan_folder(folder: Path, generated_files: list[str] | None = None, max_entries: int = 200) -> tuple[PlaceProfile, list[FileObservation]]:
    generated = set(generated_files or [])
    observations: list[FileObservation] = []

    if folder.exists():
        for index, child in enumerate(folder.iterdir()):
            if index >= max_entries:
                break
            observations.append(classify_path(child, generated_files=generated))

    place = profile_folder(folder, observations)
    return place, observations


def profile_folder(folder: Path, observations: list[FileObservation]) -> PlaceProfile:
    folder_count = sum(1 for item in observations if item.kind == "folder")
    file_count = len(observations) - folder_count
    tags: set[str] = set()

    if not observations:
        tags.add("empty_room")
    if len(observations) >= 30:
        tags.add("busy")
    if folder.name.lower() == "desktop":
        tags.add("exposed")
        tags.add("homeish")
    if sum(1 for item in observations if "picture" in item.tags) >= 5:
        tags.add("picture_room")

    return PlaceProfile(
        path=folder,
        folder_name=folder.name,
        file_count=file_count,
        folder_count=folder_count,
        food_count=sum(1 for item in observations if item.edible),
        hazard_count=sum(1 for item in observations if item.hazard),
        corpse_count=sum(1 for item in observations if item.corpse),
        tags=frozenset(tags),
    )

