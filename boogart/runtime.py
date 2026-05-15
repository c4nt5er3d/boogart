from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.debug import debug_log
from boogart.core.growth import parse_timestamp, phase_for_birth_time, stage_for_birth_time
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, remember_generated_file, save_state
from boogart.rendering.sprite import render_boogart_sprite


HEARTBEAT_SECONDS = 45
MAX_LOGS_PER_DAY = 3
MAX_TXT_PER_DAY = 1
MAX_SCAN_ENTRIES = 160
MAX_SCAN_DEPTH = 2
SENSITIVE_NAME_WORDS = {
    "abuse",
    "bank",
    "cancer",
    "divorce",
    "funeral",
    "medical",
    "password",
    "ssn",
    "tax",
}


@dataclass(frozen=True)
class RuntimeConfig:
    dev_fast: bool = False

    @classmethod
    def from_env(cls) -> "RuntimeConfig":
        return cls(dev_fast=os.environ.get("BOOGART_DEV_FAST", "").lower() in {"1", "true", "yes", "on"})


@dataclass
class HeartbeatFrame:
    paths: BoogartPaths
    now: datetime
    state: BoogartState
    config: RuntimeConfig = field(default_factory=RuntimeConfig)
    events: list[str] = field(default_factory=list)
    body_path: Path | None = None


@dataclass(frozen=True)
class SimulationResult:
    ticks: int
    events: tuple[str, ...]
    files: tuple[str, ...]
    lifecycle: str
    phase: int
    hunger: int
    current_folder: str


def heartbeat(paths: BoogartPaths, now: datetime | None = None, config: RuntimeConfig | None = None) -> str:
    frame = run_heartbeat(paths, now, config)
    return frame.events[-1] if frame.events else "idle"


def run_heartbeat(paths: BoogartPaths, now: datetime | None = None, config: RuntimeConfig | None = None) -> HeartbeatFrame:
    paths.ensure()
    frame = HeartbeatFrame(
        paths=paths,
        now=now or datetime.now(timezone.utc),
        state=load_state(paths.state_file),
        config=config or RuntimeConfig.from_env(),
    )
    reset_daily_caps(frame.state, frame.now)
    reconcile_scope(frame)
    update_phase(frame)
    inspect_body(frame)

    if frame.state.lifecycle == "alive":
        eat_food(frame)
        tick_hunger(frame)
        maybe_move(frame)
        maybe_drop_txt(frame)
        render_body(frame)
    elif frame.state.lifecycle == "dead":
        maintain_husk(frame)

    frame.state.last_active_at = frame.now.isoformat(timespec="seconds")
    frame.state.updated_at = frame.state.last_active_at
    save_state(paths.state_file, frame.state)
    debug_log(
        paths,
        "heartbeat",
        now=frame.now.isoformat(timespec="seconds"),
        lifecycle=frame.state.lifecycle,
        phase=frame.state.phase,
        hunger=frame.state.hunger,
        folder=frame.state.current_folder,
        body=frame.body_path,
        body_exists=frame.body_path.exists() if frame.body_path else False,
        events=",".join(frame.events) or "idle",
    )
    return frame


def run_simulation(
    paths: BoogartPaths,
    ticks: int,
    step: timedelta = timedelta(minutes=15),
    start: datetime | None = None,
    config: RuntimeConfig | None = None,
) -> SimulationResult:
    current = start or datetime.now(timezone.utc)
    runtime_config = config or RuntimeConfig(dev_fast=True)
    events: list[str] = []
    for index in range(max(0, ticks)):
        frame = run_heartbeat(paths, current + (step * index), runtime_config)
        events.extend(frame.events)
    state = load_state(paths.state_file)
    files = tuple(sorted(path.name for path in paths.desktop.iterdir())) if paths.desktop.exists() else ()
    return SimulationResult(
        ticks=max(0, ticks),
        events=tuple(events),
        files=files,
        lifecycle=state.lifecycle,
        phase=state.phase,
        hunger=state.hunger,
        current_folder=Path(state.current_folder).name if state.current_folder else "",
    )


def reset_daily_caps(state: BoogartState, now: datetime) -> None:
    today = now.date().isoformat()
    if state.last_log_day != today:
        state.last_log_day = today
        state.log_count_today = 0
        state.txt_count_today = 0


def reconcile_scope(frame: HeartbeatFrame) -> None:
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    roots = roaming_roots(frame.paths)
    if not any(is_within(folder, root) for root in roots):
        folder = frame.paths.desktop
    folder.mkdir(parents=True, exist_ok=True)
    frame.state.current_folder = str(folder)
    frame.body_path = folder / frame.state.body_name


def update_phase(frame: HeartbeatFrame) -> None:
    slowdown = min(frame.state.affection // 3, 60)
    if frame.config.dev_fast:
        age = frame.now - parse_timestamp(frame.state.birth_time)
        fast_phase = min(6, max(1, int(age.total_seconds() // (60 * 30)) + 1))
        frame.state.phase = max(frame.state.phase, fast_phase)
        return
    frame.state.phase = max(frame.state.phase, phase_for_birth_time(frame.state.birth_time, frame.now, slowdown))


def inspect_body(frame: HeartbeatFrame) -> None:
    if frame.body_path is None:
        return
    body_path = frame.body_path
    if not body_path.exists():
        renamed = renamed_body_candidate(body_path.parent, frame.state)
        if renamed and frame.state.phase <= 2:
            frame.state.body_name = renamed.name
            frame.body_path = renamed
            note(frame, "he lets the name sit wrong for now.")
            return
        if renamed and frame.state.phase >= 3:
            frame.state.body_name = renamed.name
            frame.body_path = renamed
            note(frame, "that isn't my name.")
            return
        kill(frame, "absence")
        return

    current_hash = file_hash(body_path)
    if frame.state.body_hash and current_hash != frame.state.body_hash:
        frame.state.memory["last_body_mismatch_at"] = frame.now.isoformat(timespec="seconds")
        if frame.state.phase >= 4:
            note(frame, "the picture forgets how it was changed.")
    frame.state.body_hash = current_hash

    copies = find_body_copies(frame)
    if copies:
        frame.state.copy_count += len(copies)
        minimum, maximum = (3, 7) if frame.config.dev_fast else (60, 180)
        delay_until = frame.now + timedelta(minutes=random_for(frame.state, "copy-delay").randint(minimum, maximum))
        frame.state.memory["copy_reaction_after"] = delay_until.isoformat(timespec="seconds")
        frame.state.memory["copy_reaction_paths"] = [str(path) for path in copies[:3]]

    maybe_react_to_copies(frame)


def eat_food(frame: HeartbeatFrame) -> None:
    foods = list(iter_food(roaming_roots(frame.paths)))
    if not foods:
        return
    food = foods[0]
    try:
        food.unlink()
    except OSError:
        return
    frame.state.hunger = max(0, frame.state.hunger - 42)
    frame.state.affection += 1
    frame.state.neglect = max(0, frame.state.neglect - 1)
    frame.events.append(f"ate:{food.name}")
    note(frame, "found something soft to eat.")


def tick_hunger(frame: HeartbeatFrame) -> None:
    if frame.now < parse_timestamp(frame.state.next_hunger_at):
        return
    frame.state.hunger = min(100, frame.state.hunger + random_for(frame.state, "hunger").randint(8, 18))
    hunger_min, hunger_max = (2, 5) if frame.config.dev_fast else (25, 95)
    frame.state.next_hunger_at = (frame.now + jitter(frame.state, "hunger-next", hunger_min, hunger_max)).isoformat(timespec="seconds")
    if frame.state.hunger >= 90:
        frame.state.neglect += 1
        note(frame, "hungry again.")
    if frame.state.hunger >= 100 and frame.state.neglect >= 6:
        kill(frame, "neglect")


def maybe_move(frame: HeartbeatFrame) -> None:
    if frame.now < parse_timestamp(frame.state.next_move_at):
        return
    if random_for(frame.state, frame.now.isoformat(timespec="minutes")).random() < 0.23:
        schedule_next_move(frame)
        return
    choices = movement_candidates(frame)
    if not choices:
        note(frame, "too quiet here.")
        schedule_next_move(frame)
        return
    destination = random_for(frame.state, "move").choice(choices)
    old_body = frame.body_path
    if old_body and old_body.exists() and old_body.name == "boogart.png":
        try:
            old_body.unlink()
        except OSError:
            pass
    frame.state.current_folder = str(destination)
    frame.state.body_name = "boogart.png"
    frame.body_path = destination / "boogart.png"
    frame.state.favorites[str(destination)] = frame.state.favorites.get(str(destination), 0) + 1
    frame.events.append(f"moved:{destination.name}")
    maybe_observe_place(frame, destination)
    schedule_next_move(frame)


def maybe_drop_txt(frame: HeartbeatFrame) -> None:
    if frame.state.txt_count_today >= MAX_TXT_PER_DAY:
        return
    if frame.now < parse_timestamp(frame.state.next_txt_at):
        return
    if frame.state.phase < 2:
        schedule_next_txt(frame)
        return

    name = "hey.txt"
    line = dialogue_line(frame)
    if frame.state.phase >= 5 and not frame.state.addressed_username:
        name = f"hey {frame.state.username}.txt"
        frame.state.addressed_username = True
    path = frame.paths.desktop / available_filename(frame.paths.desktop, name)
    try:
        path.write_text(line + "\n", encoding="utf-8")
    except OSError:
        schedule_next_txt(frame)
        return
    remember_generated_file(frame.state, path)
    frame.state.txt_count_today += 1
    frame.events.append(f"txt:{path.name}")
    schedule_next_txt(frame)


def render_body(frame: HeartbeatFrame) -> None:
    if not frame.body_path:
        debug_log(frame.paths, "render_body_skipped", reason="missing_body_path")
        return
    stage = stage_for_birth_time(frame.state.birth_time, frame.now, min(frame.state.affection // 3, 60)).id
    metadata = body_metadata(frame.state, stage)
    render_boogart_sprite(frame.body_path, stage, metadata=metadata)
    frame.state.body_hash = file_hash(frame.body_path)
    remember_generated_file(frame.state, frame.body_path)
    debug_log(frame.paths, "render_body", path=frame.body_path, exists=frame.body_path.exists(), stage=stage, hash=frame.state.body_hash)


def kill(frame: HeartbeatFrame, cause: str) -> None:
    if frame.state.lifecycle != "alive":
        return
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    corpse = folder / "boogart_dead.png"
    render_boogart_sprite(corpse, "final", metadata=body_metadata(frame.state, "final"))
    remember_generated_file(frame.state, corpse)
    frame.state.lifecycle = "dead"
    frame.state.death_count += 1
    frame.state.memory["death_cause"] = cause
    frame.state.memory["died_at"] = frame.now.isoformat(timespec="seconds")
    frame.events.append(f"dead:{cause}")
    note(frame, "mrrp.")


def maintain_husk(frame: HeartbeatFrame) -> None:
    died_at = frame.state.memory.get("died_at")
    if not died_at:
        return
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    corpse = folder / "boogart_dead.png"
    husk = folder / "boogart_husk.png"
    husk_after = timedelta(minutes=10) if frame.config.dev_fast else timedelta(hours=48)
    if frame.now - parse_timestamp(str(died_at)) >= husk_after:
        if not husk.exists():
            render_boogart_sprite(husk, "wrong", metadata=body_metadata(frame.state, "wrong"))
            remember_generated_file(frame.state, husk)
        return
    if not corpse.exists():
        render_boogart_sprite(corpse, "final", metadata=body_metadata(frame.state, "final"))
        remember_generated_file(frame.state, corpse)


def note(frame: HeartbeatFrame, line: str) -> None:
    if frame.state.log_count_today >= MAX_LOGS_PER_DAY:
        return
    try:
        frame.paths.log_file.parent.mkdir(parents=True, exist_ok=True)
        with frame.paths.log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"[{frame.now.astimezone().strftime('%Y-%m-%d %H:%M')}]: {line}\n")
    except OSError:
        return
    frame.state.log_count_today += 1
    remember_generated_file(frame.state, frame.paths.log_file)


def maybe_observe_place(frame: HeartbeatFrame, folder: Path) -> None:
    if frame.state.phase < 3:
        return
    entries = safe_entries(folder)
    names = [entry.name for entry in entries if is_safe_name(entry.name)]
    if not names:
        return
    if len(entries) >= 30:
        note(frame, "this folder seems busy.")
        return
    repeated = repeated_token(names)
    if repeated:
        note(frame, f'things keep being called "{repeated}".')


def dialogue_line(frame: HeartbeatFrame) -> str:
    if frame.state.lifecycle == "dead":
        return "not here."
    if frame.state.hunger >= 85:
        return "there is nothing in here."
    if frame.state.phase >= 5 and frame.state.affection >= 6:
        return "i remember when you used to check on me."
    if frame.state.phase >= 4 and frame.state.copy_count:
        return "too many."
    return random_for(frame.state, "dialogue").choice(("hey.", "still here.", "heard something move."))


def maybe_react_to_copies(frame: HeartbeatFrame) -> None:
    raw_after = frame.state.memory.get("copy_reaction_after")
    if not raw_after or frame.now < parse_timestamp(str(raw_after)):
        return
    paths = [Path(str(value)) for value in frame.state.memory.get("copy_reaction_paths", []) if isinstance(value, str)]
    for path in paths:
        note_path = path.with_name("too many.txt")
        try:
            note_path.write_text("too many.\n", encoding="utf-8")
        except OSError:
            continue
        remember_generated_file(frame.state, note_path)
    frame.state.memory.pop("copy_reaction_after", None)
    frame.state.memory.pop("copy_reaction_paths", None)


def movement_candidates(frame: HeartbeatFrame) -> list[Path]:
    candidates: list[Path] = []
    for root in roaming_roots(frame.paths):
        candidates.extend(path for path in iter_dirs(root) if is_roamable(path))
    return candidates or [frame.paths.desktop]


def iter_food(roots: tuple[Path, ...]):
    for root in roots:
        for path in bounded_walk(root):
            if path.is_file() and path.suffix.lower() == ".food":
                yield path


def iter_dirs(root: Path):
    for path in bounded_walk(root):
        if path.is_dir():
            yield path


def bounded_walk(root: Path):
    if not root.exists():
        return
    stack = [(root, 0)]
    seen = 0
    while stack and seen < MAX_SCAN_ENTRIES:
        folder, depth = stack.pop()
        for child in safe_entries(folder):
            seen += 1
            yield child
            if seen >= MAX_SCAN_ENTRIES:
                return
            if depth < MAX_SCAN_DEPTH and child.is_dir() and is_roamable(child):
                stack.append((child, depth + 1))


def safe_entries(folder: Path) -> list[Path]:
    try:
        return sorted(folder.iterdir(), key=lambda path: path.name.lower())[:MAX_SCAN_ENTRIES]
    except OSError:
        return []


def roaming_roots(paths: BoogartPaths) -> tuple[Path, ...]:
    roots = [paths.desktop, paths.downloads]
    return tuple(root for root in roots if root.exists())


def is_roamable(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.startswith("."):
        return False
    return not any(word in lowered for word in ("onedrive", "dropbox", "icloud", "$recycle", "node_modules", "__pycache__"))


def find_body_copies(frame: HeartbeatFrame) -> list[Path]:
    copies: list[Path] = []
    for root in roaming_roots(frame.paths):
        for path in bounded_walk(root):
            if path == frame.body_path:
                continue
            if path.is_file() and path.name.lower().startswith("boogart") and path.suffix.lower() == ".png":
                copies.append(path)
    return copies[:5]


def renamed_body_candidate(folder: Path, state: BoogartState) -> Path | None:
    candidates = [path for path in safe_entries(folder) if path.is_file() and path.suffix.lower() == ".png" and path.name not in {"boogart_dead.png", "boogart_husk.png"}]
    if len(candidates) == 1:
        return candidates[0]
    if state.body_name != "boogart.png":
        candidate = folder / state.body_name
        if candidate.exists():
            return candidate
    return None


def schedule_next_move(frame: HeartbeatFrame) -> None:
    minimum, maximum = (1, 3) if frame.config.dev_fast else (4, 39)
    frame.state.next_move_at = (frame.now + jitter(frame.state, "move-next", minimum, maximum)).isoformat(timespec="seconds")


def schedule_next_txt(frame: HeartbeatFrame) -> None:
    minimum, maximum = (8, 15) if frame.config.dev_fast else (20 * 60, 32 * 60)
    frame.state.next_txt_at = (frame.now + jitter(frame.state, "txt-next", minimum, maximum)).isoformat(timespec="seconds")


def jitter(state: BoogartState, salt: str, minimum_minutes: int, maximum_minutes: int) -> timedelta:
    return timedelta(minutes=random_for(state, salt).randint(minimum_minutes, maximum_minutes))


def random_for(state: BoogartState, salt: str) -> random.Random:
    return random.Random(f"{state.boogart_id}:{state.generation}:{salt}:{state.hunger}")


def body_metadata(state: BoogartState, stage: str) -> dict[str, str]:
    return {
        "boogart_id": state.boogart_id,
        "generation": str(state.generation),
        "birth_time": state.birth_time,
        "stage": stage,
        "lineage": ",".join(state.lineage),
        "parent_id": state.parent_id or "",
        "death_count": str(state.death_count),
        "copy_count": str(state.copy_count),
        "body_hash": "",
    }


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def available_filename(folder: Path, filename: str) -> str:
    path = folder / filename
    if not path.exists():
        return filename
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 50):
        candidate = f"{stem} ({index}){suffix}"
        if not (folder / candidate).exists():
            return candidate
    return f"{stem} ({random.randint(50, 999)}){suffix}"


def repeated_token(names: list[str]) -> str | None:
    counts: dict[str, int] = {}
    for name in names:
        for token in name.lower().replace("_", " ").replace("-", " ").split():
            if len(token) < 4 or token in SENSITIVE_NAME_WORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
    if not counts:
        return None
    token, count = max(counts.items(), key=lambda item: item[1])
    return token if count >= 3 else None


def is_safe_name(name: str) -> bool:
    lowered = name.lower()
    return not any(word in lowered for word in SENSITIVE_NAME_WORDS)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False
