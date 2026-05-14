from __future__ import annotations

from pathlib import Path

from boogart.world.classifiers import classify_path
from boogart.world.observations import FileObservation, PlaceProfile
from boogart.world.scope import is_hidden_or_systemish, safe_iterdir


MAX_TREE_DEPTH = 2
MAX_FILES_PER_FOLDER = 100
MAX_TOTAL_OBSERVATIONS = 1000


def scan_folder(folder: Path, generated_files: list[str] | None = None, max_entries: int = 200) -> tuple[PlaceProfile, list[FileObservation]]:
    generated = set(generated_files or [])
    observations: list[FileObservation] = []

    if folder.exists():
        for index, child in enumerate(safe_iterdir(folder)):
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
    if sum(1 for item in observations if "code" in item.tags) >= 3 or any("project" in item.tags for item in observations):
        tags.add("code_room")
    if sum(1 for item in observations if "document" in item.tags) >= 5:
        tags.add("paper_room")
    if sum(1 for item in observations if "music" in item.tags) >= 3:
        tags.add("music_room")
    if sum(1 for item in observations if "video" in item.tags) >= 3:
        tags.add("video_room")

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


def scan_tree(
    roots: tuple[Path, ...],
    generated_files: list[str] | None = None,
    max_depth: int = MAX_TREE_DEPTH,
    max_files_per_folder: int = MAX_FILES_PER_FOLDER,
    max_total: int = MAX_TOTAL_OBSERVATIONS,
) -> list[FileObservation]:
    generated = set(generated_files or [])
    observations: list[FileObservation] = []
    for root in roots:
        scan_tree_into(root, generated, observations, max_depth, max_files_per_folder, max_total)
        if len(observations) >= max_total:
            break
    return observations


def scan_tree_into(
    folder: Path,
    generated: set[str],
    observations: list[FileObservation],
    depth_remaining: int,
    max_files_per_folder: int,
    max_total: int,
) -> None:
    if len(observations) >= max_total or not folder.exists() or is_hidden_or_systemish(folder):
        return

    children = safe_iterdir(folder)[:max_files_per_folder]
    for child in children:
        if len(observations) >= max_total:
            return
        observations.append(classify_path(child, generated_files=generated))

    if depth_remaining <= 0:
        return

    for child in children:
        if child.is_dir():
            scan_tree_into(child, generated, observations, depth_remaining - 1, max_files_per_folder, max_total)
