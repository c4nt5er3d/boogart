from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from boogart.core.growth import parse_timestamp
from boogart.core.lifecycle import track_generated_file
from boogart.core.log import append_log
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state
from boogart.mind.brain import tick_state
from boogart.mind.context import BrainResult
from boogart.rendering.sprite import render_boogart_sprite


HEARTBEAT_SECONDS = 45


def heartbeat(paths: BoogartPaths, now: datetime | None = None) -> BrainResult:
    current_time = now or datetime.now(timezone.utc)
    state = load_state(paths.state_file)
    folder = Path(state.current_folder or paths.desktop)
    folder.mkdir(parents=True, exist_ok=True)

    previous_folder = folder
    result = tick_state(state, folder, current_time)
    active_folder = Path(state.current_folder or previous_folder)
    active_folder.mkdir(parents=True, exist_ok=True)

    if state.lifecycle == "alive":
        sprite_path = active_folder / "boogart.png"
        render_boogart_sprite(sprite_path, state.stage)
        track_generated_file(state, sprite_path)

    append_log(paths.log_file, heartbeat_log_line(state, result, current_time))
    save_state(paths.state_file, state)
    return result


def heartbeat_log_line(state: BoogartState, result: BrainResult, now: datetime) -> str:
    day = max(1, (now - parse_timestamp(state.birth_at)).days + 1)
    message = result.message or result.action_id
    return f"[day {day} / {state.stage} / {state.lifecycle}] {message}"
