from __future__ import annotations

import re
from pathlib import Path


def dialogue_note_path(desktop: Path, username: str) -> Path:
    safe_name = re.sub(r'[<>:"/\\\\|?*\\x00-\\x1f]', "", username).strip() or "friend"
    return desktop / f"hey {safe_name}.txt"


def drop_dialogue_note(desktop: Path, username: str, line: str) -> Path:
    path = dialogue_note_path(desktop, username)
    text = line or "you made room for me."
    path.write_text(text + "\n", encoding="utf-8")
    return path
