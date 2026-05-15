from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boogart.core.paths import BoogartPaths, debug_paths


def debug_log(paths: BoogartPaths, event: str, **fields: object) -> None:
    try:
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        line = format_debug_line(event, fields)
        with paths.debug_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        return


def format_debug_line(event: str, fields: dict[str, object]) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    details = " ".join(f"{key}={format_debug_value(value)}" for key, value in sorted(fields.items()))
    return f"[{timestamp}] {event}" + (f" {details}" if details else "")


def format_debug_value(value: object) -> str:
    text = str(value).replace("\n", "\\n")
    if " " in text:
        return repr(text)
    return text


def debug_status(paths: BoogartPaths) -> str:
    lines = ["BOOGART DEBUG STATUS", ""]
    for key, value in debug_paths(paths).items():
        path = Path(value)
        exists = path.exists()
        lines.append(f"{key}: {value} exists={exists}")
    if paths.debug_file.exists():
        lines.append("")
        lines.append("recent debug:")
        lines.extend(paths.debug_file.read_text(encoding="utf-8", errors="replace").splitlines()[-20:])
    return "\n".join(lines)
