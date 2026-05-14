from __future__ import annotations

import re
from pathlib import Path

from boogart.world.observations import FileObservation


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
DOCUMENT_EXTENSIONS = {".doc", ".docx", ".pdf", ".txt", ".rtf", ".md", ".xls", ".xlsx"}
WEIRD_WORDS = {"blood", "teeth", "bone", "battery", "glass", "rot", "dead", "cursed", "wire"}
IMPORTANT_WORDS = {"tax", "taxes", "resume", "password", "final", "invoice", "contract"}
PERSONALISH_WORDS = {"mom", "dad", "birthday", "wedding", "home", "old", "photo", "family"}
HAZARD_NAMES = {"slipperyfloor", "badwire", "coldspot", "sharpcorner"}
BOOGART_NAMES = {"boogart.png", "boogart_log.txt", "dead_boogart.png", "stain_boogart.png"}


def classify_path(path: Path, generated_files: set[str] | None = None) -> FileObservation:
    generated = generated_files or set()
    name = path.name
    lowered = name.lower()
    extension = path.suffix.lower()
    kind = "folder" if path.is_dir() else "file"
    stem_words = set(re.findall(r"[a-z0-9]+", path.stem.lower()))
    tags: set[str] = set()
    emotional_weight = 0

    if kind == "folder":
        tags.add("folder")
    if extension == ".food":
        tags.add("food")
        emotional_weight += 1
    if extension == ".hazard" or path.stem.lower() in HAZARD_NAMES:
        tags.add("hazard")
        emotional_weight += 3
    if extension == ".gift":
        tags.add("gift")
    if lowered == "dead_boogart.png":
        tags.add("corpse")
        emotional_weight += 5
    if lowered in BOOGART_NAMES or str(path) in generated:
        tags.add("boogart_owned")
    if extension in IMAGE_EXTENSIONS:
        tags.add("picture")
    if extension in DOCUMENT_EXTENSIONS:
        tags.add("document")
    if extension in {".lnk", ".url"}:
        tags.add("shortcut")
    if "final" in stem_words and re.search(r"final.*final", path.stem, re.IGNORECASE):
        tags.add("repeated_final")
        emotional_weight += 2
    if stem_words & IMPORTANT_WORDS:
        tags.add("important")
        emotional_weight += 1
    if stem_words & PERSONALISH_WORDS:
        tags.add("personalish")
        emotional_weight += 1
    if stem_words & WEIRD_WORDS:
        tags.add("weird")
        emotional_weight += 2

    return FileObservation(
        path=path,
        name=name,
        extension=extension,
        kind=kind,
        tags=frozenset(tags),
        edible=extension == ".food",
        hazard="hazard" in tags,
        corpse="corpse" in tags,
        boogart_owned="boogart_owned" in tags,
        emotional_weight=emotional_weight,
    )

