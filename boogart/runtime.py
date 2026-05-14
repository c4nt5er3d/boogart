from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from boogart.core.filesystem import FileSystemAdapter
from boogart.core.growth import parse_timestamp
from boogart.core.lifecycle import track_generated_file
from boogart.core.log import append_log
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, save_state
from boogart.mind.appraisal import AppraisalResult, appraise
from boogart.mind.brain import tick_state
from boogart.mind.context import BrainResult
from boogart.mind.messages import MessageDecision, MessageDirector
from boogart.mind.needs import apply_need_drift, ensure_need_memory
from boogart.rendering.sprite import render_boogart_sprite
from boogart.world.observations import FileObservation, PlaceProfile
from boogart.world.scanner import scan_folder, scan_tree
from boogart.world.scope import allowed_roots, is_allowed_path
from boogart.world.watcher import snapshot_folder, time_aware_comments, update_watcher_memory


HEARTBEAT_SECONDS = 45


@dataclass
class HeartbeatFrame:
    paths: BoogartPaths
    now: datetime
    state: BoogartState
    roots: tuple[Path, ...]
    folder: Path
    fs: FileSystemAdapter
    place: PlaceProfile | None = None
    observations: list[FileObservation] = field(default_factory=list)
    appraisal: AppraisalResult | None = None
    action: BrainResult | None = None
    active_folder: Path | None = None
    watcher_comments: list[str] = field(default_factory=list)
    messages: list[MessageDecision] = field(default_factory=list)


def heartbeat(paths: BoogartPaths, now: datetime | None = None) -> BrainResult:
    frame = run_heartbeat(paths, now)
    return frame.action or BrainResult("idle")


def run_heartbeat(paths: BoogartPaths, now: datetime | None = None) -> HeartbeatFrame:
    frame = load_frame(paths, now)
    perceive(frame)
    update_needs(frame)
    decide_action(frame)
    render_frame(frame)
    collect_watcher_comments(frame)
    decide_messages(frame)
    update_scope_tree_memory(frame.state, frame.roots)
    persist_frame(frame)
    return frame


def load_frame(paths: BoogartPaths, now: datetime | None = None) -> HeartbeatFrame:
    current_time = now or datetime.now(timezone.utc)
    state = load_state(paths.state_file)
    roots = allowed_roots(paths, state)
    folder = Path(state.current_folder or paths.desktop)
    if not is_allowed_path(folder, roots):
        folder = paths.desktop
        state.current_folder = str(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fs = FileSystemAdapter(roots)
    return HeartbeatFrame(paths=paths, now=current_time, state=state, roots=roots, folder=folder, fs=fs)


def perceive(frame: HeartbeatFrame) -> None:
    place, observations = scan_folder(frame.folder, generated_files=frame.state.generated_files)
    frame.place = place
    frame.observations = observations
    frame.appraisal = appraise(place, observations)


def update_needs(frame: HeartbeatFrame) -> None:
    if frame.appraisal is None:
        raise RuntimeError("cannot update needs before appraisal")
    apply_need_drift(frame.state, frame.appraisal, frame.now)


def decide_action(frame: HeartbeatFrame) -> None:
    previous_folder = frame.folder
    if frame.place is None or frame.appraisal is None:
        raise RuntimeError("cannot decide action before perception")
    frame.action = tick_state(
        frame.state,
        frame.folder,
        frame.now,
        fs=frame.fs,
        place=frame.place,
        observations=frame.observations,
        appraisal=frame.appraisal,
        needs=ensure_need_memory(frame.state),
    )
    frame.active_folder = Path(frame.state.current_folder or previous_folder)
    frame.active_folder.mkdir(parents=True, exist_ok=True)


def render_frame(frame: HeartbeatFrame) -> None:
    if frame.action and frame.action.action_id == "die" and frame.action.path:
        render_boogart_sprite(frame.action.path, "final")
        track_generated_file(frame.state, frame.action.path)
        return
    if frame.state.lifecycle != "alive":
        return
    active_folder = frame.active_folder or frame.folder
    sprite_path = active_folder / "boogart.png"
    render_boogart_sprite(sprite_path, frame.state.stage)
    track_generated_file(frame.state, sprite_path)


def collect_watcher_comments(frame: HeartbeatFrame) -> None:
    active_folder = frame.active_folder or frame.folder
    frame.watcher_comments = watcher_comments(frame.state, active_folder, frame.now)


def decide_messages(frame: HeartbeatFrame) -> None:
    action = frame.action or BrainResult("idle")
    frame.messages = MessageDirector().decisions(frame.state, action, frame.watcher_comments, frame.now)


def persist_frame(frame: HeartbeatFrame) -> None:
    for decision in frame.messages:
        append_log(frame.paths.log_file, message_log_line(frame.state, decision, frame.now))
    save_state(frame.paths.state_file, frame.state)


def message_log_line(state: BoogartState, decision: MessageDecision, now: datetime) -> str:
    day = max(1, (now - parse_timestamp(state.birth_at)).days + 1)
    return f"[day {day} / {decision.prefix} / {state.stage}] {decision.text}"


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
