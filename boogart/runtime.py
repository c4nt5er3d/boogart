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
from boogart.world.scanner import scan_folder, scan_tree
from boogart.world.scope import allowed_roots, is_allowed_path
from boogart.world.watcher import snapshot_folder, time_aware_comments, update_watcher_memory


HEARTBEAT_SECONDS = 45


def heartbeat(paths: BoogartPaths, now: datetime | None = None) -> BrainResult:
    current_time = now or datetime.now(timezone.utc)
    state = load_state(paths.state_file)
    roots = allowed_roots(paths, state)
    folder = Path(state.current_folder or paths.desktop)
    if not is_allowed_path(folder, roots):
        folder = paths.desktop
        state.current_folder = str(folder)
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
    for comment in watcher_comments(state, active_folder, current_time):
        append_log(paths.log_file, haunting_log_line(state, comment, current_time))
    update_scope_tree_memory(state, roots)
    save_state(paths.state_file, state)
    return result


def heartbeat_log_line(state: BoogartState, result: BrainResult, now: datetime) -> str:
    day = max(1, (now - parse_timestamp(state.birth_at)).days + 1)
    message = result.message or result.action_id
    return f"[day {day} / {state.stage} / {state.lifecycle}] {message}"


def haunting_log_line(state: BoogartState, comment: str, now: datetime) -> str:
    day = max(1, (now - parse_timestamp(state.birth_at)).days + 1)
    if state.corruption >= 60:
        prefix = "SYSTEM COMPROMISE"
    elif state.corruption >= 25:
        prefix = "signal"
    else:
        prefix = "boogart"
    return f"[day {day} / {prefix}] {comment}"


def watcher_comments(state: BoogartState, folder: Path, now: datetime) -> list[str]:
    place, observations = scan_folder(folder, generated_files=state.generated_files)
    snapshot = snapshot_folder(place, observations)
    comments = update_watcher_memory(state, snapshot)
    comments.extend(time_aware_comments(state, now.hour))
    return comments


def update_scope_tree_memory(state: BoogartState, roots: tuple[Path, ...]) -> None:
    observations = scan_tree(roots, generated_files=state.generated_files)
    tag_counts: dict[str, int] = {}
    for observation in observations:
        for tag in observation.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    state.global_memory["scope_tree"] = {
        "roots": [str(root) for root in roots],
        "observation_count": len(observations),
        "tag_counts": tag_counts,
    }
