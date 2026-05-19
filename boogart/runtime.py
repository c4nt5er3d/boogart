from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from boogart.core.debug import debug_log
from boogart.core.growth import STAGE_IDS, parse_timestamp, phase_for_birth_time, stage_for_birth_time
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, remember_generated_file, save_state
from boogart.rendering.png import read_png_metadata
from boogart.rendering.sprite import render_boogart_sprite


HEARTBEAT_SECONDS = 45
FIRST_MOVE_GRACE = timedelta(minutes=10)
FIRST_DAY_VISIBILITY = timedelta(hours=24)
DEV_FAST_FIRST_MOVE_GRACE = timedelta(seconds=10)
DEV_FAST_FIRST_DAY_VISIBILITY = timedelta(minutes=1)
MAX_LOGS_PER_DAY = 3
MAX_TXT_PER_DAY = 1
MAX_SCAN_ENTRIES = 160
MAX_SCAN_DEPTH = 2
FIRST_SESSION_PROTECTION = timedelta(hours=2)
FIRST_STARVATION_ACTIVE_MINUTES = 72 * 60
LATER_STARVATION_ACTIVE_MINUTES = 48 * 60
STARVATION_DEATH_COOLDOWN_ACTIVE_MINUTES = 7 * 24 * 60
MAX_ACTIVE_DELTA_MINUTES = 60
FOOD_HUNGER_REDUCTION = 55
CORPSE_HUNGER_REDUCTION = 80
CORPSE_BITE_COUNT = 3
MAX_CANNIBAL_BLOOD_LEVEL = 3
MAX_BURROWS_TOTAL = 48
MAX_BURROWS_PER_DAY = 1
MAX_NEST_ARTIFACTS_TOTAL = 120
MAX_GENERATED_FILES_TOTAL = 250
NOTE_NAME_SEQUENCE = (
    "hello.txt",
    "is anyone there.txt",
    "i found something.txt",
    "the walls are thin.txt",
    "it's quiet here.txt",
    "don't leave yet.txt",
    "stay.txt",
    "where did you go.txt",
    "i'm still here.txt",
    "wait.txt",
)
STRANGE_FOLDER_WORDS = {
    "build",
    "cache",
    "delta",
    "dist",
    "node_modules",
    "runtime",
    "target",
    "temp",
    "tmp",
    "venv",
    ".git",
}
SENSITIVE_NAME_WORDS = {
    "abuse",
    "bank",
    "cancer",
    "court",
    "dead",
    "death",
    "debt",
    "divorce",
    "drug",
    "funeral",
    "health",
    "hospital",
    "medical",
    "money",
    "password",
    "police",
    "prison",
    "private",
    "psych",
    "secret",
    "ssn",
    "suicide",
    "tax",
    "therapy",
    "trauma",
    "victim",
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
    track_active_time(frame)
    ensure_starvation_memory(frame)
    update_phase(frame)
    inspect_body(frame)
    check_territory_health(frame)
    maybe_find_corpse(frame)
    schedule_copy_reaction(frame, find_body_copies(frame))
    maybe_react_to_copies(frame)

    # Secret Ending: Containment check
    if check_containment(frame):
        frame.state.last_active_at = frame.now.isoformat(timespec="seconds")
        frame.state.updated_at = frame.state.last_active_at
        save_state(paths.state_file, frame.state)
        return frame

    if frame.state.lifecycle == "alive":
        # Narrative: Lineage awareness
        if len(frame.state.lineage) > 1 and not frame.state.memory.get("reacted_to_lineage"):
            if random_for(frame.state, "lineage").random() < 0.1:
                note(frame, "i remember a different sky.")
                frame.state.memory["reacted_to_lineage"] = True

        eat_food(frame)
        if frame.state.lifecycle == "alive":
            tick_hunger(frame)
        if frame.state.lifecycle == "alive":
            maintain_starvation(frame)
        if frame.state.lifecycle == "alive":
            maybe_move(frame)
        if frame.state.lifecycle == "alive":
            maybe_drop_txt(frame)
        if frame.state.lifecycle == "alive":
            maybe_nest(frame)
        if frame.state.lifecycle == "alive":
            maybe_burrow(frame)
        if frame.state.lifecycle == "alive":
            render_body(frame)
    elif frame.state.lifecycle == "dead":
        maintain_husk(frame)

    # Expose State Information
    desperation = "calm"
    if frame.state.hunger > 80:
        desperation = "frantic"
    elif frame.state.hunger > 50:
        desperation = "uneasy"

    status = f"state:Gen {frame.state.generation} | Phase {frame.state.phase} ({frame.state.phase_name}) | Hunger {frame.state.hunger} ({desperation})"
    frame.events.append(status)

    frame.state.last_active_at = frame.now.isoformat(timespec="seconds")
    frame.state.updated_at = frame.state.last_active_at
    if not save_state(paths.state_file, frame.state):
        debug_log(paths, "save_state_failed", path=paths.state_file)
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
        state.nest_count_today = 0
        state.memory["burrow_day"] = today
        state.memory["burrow_count_today"] = 0

        # Polish: Favorite Decay (attachments fade if not maintained)
        new_favorites = {}
        for folder, count in state.favorites.items():
            if count > 1:
                new_favorites[folder] = count - 1
        state.favorites = new_favorites


def reconcile_scope(frame: HeartbeatFrame) -> None:
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    roots = roaming_roots(frame.paths)
    allowed_roots = (*roots, *trash_locations(frame.paths))
    if not any(is_within(folder, root) for root in allowed_roots):
        folder = frame.paths.desktop
    folder.mkdir(parents=True, exist_ok=True)
    frame.state.current_folder = str(folder)
    frame.body_path = folder / frame.state.body_name


def track_active_time(frame: HeartbeatFrame) -> None:
    delta = active_delta_minutes(frame)
    if delta <= 0:
        return
    frame.state.memory["active_minutes_total"] = int(frame.state.memory.get("active_minutes_total", 0) or 0) + delta


def active_delta_minutes(frame: HeartbeatFrame) -> int:
    last_active = parse_timestamp(frame.state.last_active_at)
    if frame.now <= last_active:
        return 0
    minutes = int((frame.now - last_active).total_seconds() // 60)
    return max(0, min(MAX_ACTIVE_DELTA_MINUTES, minutes))


def ensure_starvation_memory(frame: HeartbeatFrame) -> None:
    if not frame.state.memory.get("first_session_until"):
        first_session_until = parse_timestamp(frame.state.birth_time) + FIRST_SESSION_PROTECTION
        frame.state.memory["first_session_until"] = first_session_until.isoformat(timespec="seconds")
    frame.state.neglect = 0


def maintain_starvation(frame: HeartbeatFrame) -> None:
    if frame.state.hunger < 100:
        clear_starvation(frame)
        return

    if frame.now < parse_timestamp(str(frame.state.memory.get("first_session_until"))):
        return

    delta = active_delta_minutes(frame)
    if delta <= 0:
        return

    if not frame.state.memory.get("starving_since"):
        frame.state.memory["starving_since"] = frame.now.isoformat(timespec="seconds")
        frame.state.memory["active_starving_minutes"] = 0
        note(frame, "the bowl is only a shape now.")
        return

    active_starving = int(frame.state.memory.get("active_starving_minutes", 0) or 0) + delta
    frame.state.memory["active_starving_minutes"] = active_starving

    threshold = FIRST_STARVATION_ACTIVE_MINUTES
    if frame.state.memory.get("last_starvation_death_at"):
        threshold = LATER_STARVATION_ACTIVE_MINUTES
    if active_starving < threshold:
        return

    active_total = int(frame.state.memory.get("active_minutes_total", 0) or 0)
    last_death_active = int(frame.state.memory.get("last_starvation_death_active_at", -STARVATION_DEATH_COOLDOWN_ACTIVE_MINUTES) or 0)
    if active_total - last_death_active < STARVATION_DEATH_COOLDOWN_ACTIVE_MINUTES:
        return

    frame.state.memory["last_starvation_death_at"] = frame.now.isoformat(timespec="seconds")
    frame.state.memory["last_starvation_death_active_at"] = active_total
    kill(frame, "starvation")


def clear_starvation(frame: HeartbeatFrame) -> None:
    frame.state.memory.pop("starving_since", None)
    frame.state.memory["active_starving_minutes"] = 0
    frame.state.memory["last_fed_at"] = frame.now.isoformat(timespec="seconds")


def update_phase(frame: HeartbeatFrame) -> None:
    old_phase = frame.state.phase
    slowdown = min(frame.state.affection // 3, 60)
    if frame.config.dev_fast:
        age = frame.now - parse_timestamp(frame.state.birth_time)
        fast_phase = min(6, max(1, int(age.total_seconds() // 120) + 1))
        frame.state.phase = max(frame.state.phase, fast_phase)
    else:
        frame.state.phase = max(frame.state.phase, phase_for_birth_time(frame.state.birth_time, frame.now, slowdown))

    if frame.state.phase > old_phase:
        note(frame, f"the creature's movements feel... {frame.state.phase_name.lower()}.")
        frame.events.append(f"phase_transition:{old_phase}->{frame.state.phase}")


def inspect_body(frame: HeartbeatFrame) -> None:
    if frame.body_path is None:
        return
    body_path = frame.body_path
    if not body_path.exists():
        # Check if he was moved within the SAME folder (renaming)
        renamed = renamed_body_candidate(body_path.parent, frame.state)
        if renamed:
            frame.state.body_name = renamed.name
            frame.body_path = renamed
            if frame.state.phase <= 2:
                note(frame, "he lets the name sit wrong for now.")
            else:
                note(frame, "that isn't my name.")
            return

        # NEW: Check if he was moved to a DIFFERENT folder (Manual Move)
        found = find_missing_body(frame)
        if found:
            old_folder = body_path.parent
            frame.state.current_folder = str(found.parent)
            frame.state.body_name = found.name
            frame.body_path = found

            if found.parent != old_folder:
                if not frame.state.memory.get("manual_move_logged"):
                    note(frame, "the house changed its shape.")
                    frame.state.memory["manual_move_logged"] = True
                    frame.state.memory["manual_move_logged_at"] = frame.now.isoformat(timespec="seconds")

            react_to_manual_move(frame, found.parent)
            return

        # GDD: If the root is gone (unplugged drive), it's just absence (silence).
        if not body_path.parent.exists():
            debug_log(frame.paths, "body_missing_silent", path=body_path)
            return

        kill(frame, "deleted")
        return

    # Verify identity if it's a PNG
    if body_path.suffix.lower() == ".png":
        meta = read_png_metadata(body_path)
        if meta and "boogart_id" in meta and meta["boogart_id"] != frame.state.boogart_id:
            # This is someone else's Boogart!
            note(frame, "this isn't me.")
            kill(frame, "absence")
            return

    current_hash = file_hash(body_path)
    if frame.state.body_hash and current_hash != frame.state.body_hash:
        frame.state.memory["last_body_mismatch_at"] = frame.now.isoformat(timespec="seconds")
        if frame.state.phase >= 4:
            note(frame, "the picture forgets how it was changed.")
        elif frame.state.phase >= 3:
            note(frame, random_for(frame.state, "skin").choice((
                "someone touched my skin.",
                "the picture is different. it feels better now.",
                "i felt that."
            )))
    frame.state.body_hash = current_hash


def check_territory_health(frame: HeartbeatFrame) -> None:
    if frame.state.phase < 2:
        return

    # Polish: Reactive Territory
    # Check if any .was_here files we left have been deleted by the user
    ghost_paths = [Path(p) for p in frame.state.generated_files if str(p).endswith(".was_here")]
    if not ghost_paths:
        return

    missing_count = 0
    new_generated_files = list(frame.state.generated_files)

    for path in ghost_paths:
        if not path.exists():
            missing_count += 1
            if str(path) in new_generated_files:
                new_generated_files.remove(str(path))

    if missing_count > 0:
        frame.state.generated_files = new_generated_files
        if not repeated_recently(frame, "territory_deleted_at", days=3):
            note(frame, "someone moved my marks.")
            frame.state.memory["territory_deleted_at"] = frame.now.isoformat(timespec="seconds")


def check_containment(frame: HeartbeatFrame) -> bool:
    if frame.state.phase < 6 or frame.state.lifecycle != "alive":
        return False

    current_folder = Path(frame.state.current_folder or frame.paths.desktop)
    tether_in_current = current_folder / ".boogart_tether"

    # If a NEW tether is created in the current folder, and the ROOT tether is missing
    if tether_in_current.exists() and not frame.paths.tether_file.exists():
        note(frame, f"[SYSTEM]: PROCESS CONTAINED. ARCHIVING ID: {frame.state.boogart_id}. DISCONNECTING.", force=True)
        frame.state.lifecycle = "contained"

        # Transform body into a core dump
        body_path = current_folder / frame.state.body_name
        if body_path.exists():
            try:
                dump_path = current_folder / "core.dump"
                body_path.rename(dump_path)
                frame.state.body_name = "core.dump"
            except OSError:
                pass

        frame.events.append("contained")
        return True
    return False


def maybe_find_corpse(frame: HeartbeatFrame) -> None:
    if frame.body_path is None:
        return
    body_path = frame.body_path

    # GDD: Finding a previous corpse
    if frame.state.lifecycle == "alive":
        corpse = body_path.parent / "boogart_dead.png"
        husk = body_path.parent / "boogart_husk.png"
        if (corpse.exists() or husk.exists()) and not frame.state.memory.get("reacted_to_corpse"):
            note_many(frame, ("found something.", "not sure what it is.", "it looks like me."))
            frame.state.memory["reacted_to_corpse"] = True


def eat_food(frame: HeartbeatFrame) -> None:
    # GDD: Cannibalism interaction
    # He eats ANY boogart corpse he finds in his roaming roots.
    # We eat up to 3 things per heartbeat if hungry.
    for _ in range(3):
        if frame.state.hunger < 10:
            break

        corpses = [corpse for corpse in iter_corpses(roaming_roots(frame.paths)) if can_eat_corpse(frame, corpse)]
        if corpses:
            corpse = corpses[0]
            target_str = str(corpse)
            if frame.state.memory.get("food_target") != target_str:
                frame.state.memory["food_target"] = target_str
                note(frame, "found something.")
                return

            if bite_corpse(frame, corpse):
                return

        foods = list(iter_food(roaming_roots(frame.paths)))
        if not foods:
            break

        food = foods[0]
        # Polish: Slow bite for .food files
        target_str = str(food)
        if frame.state.memory.get("food_target") != target_str:
            frame.state.memory["food_target"] = target_str
            note(frame, "found something.")
            return

        try:
            food.unlink()
            frame.state.hunger = max(0, frame.state.hunger - FOOD_HUNGER_REDUCTION)
            frame.state.affection += 1
            clear_starvation(frame)
            frame.state.memory.pop("food_target", None)

            # Polish: Feeding residue (crumbs/bones) as PNG
            if can_create_artifact(frame, "nest") and random_for(frame.state, f"residue-{food.name}").random() < 0.3:
                res_name = random_for(frame.state, "res-type").choice(("crumbs.png", "bone.png", "dust.png"))
                res_filename = available_filename(food.parent, res_name)
                if not res_filename:
                    continue
                res_path = food.parent / res_filename
                try:
                    render_boogart_sprite(res_path, "residue", metadata=artifact_metadata(frame.state, "residue", "food"))
                    remember_generated_file(frame.state, res_path)
                except OSError:
                    pass

            # Polish: Varied eating logs
            if frame.state.phase <= 2:
                line = random_for(frame.state, "eat").choice(("the static stopped for a second.", "a brief, cold comfort.", "still hungry."))
            elif frame.state.phase <= 4:
                line = random_for(frame.state, "eat").choice(("it's too quiet when i eat.", "i can taste the data.", "it tasted like a forgotten secret."))
            else:
                line = random_for(frame.state, "eat").choice(("nothing satisfies.", "it tasted like the house.", "it was cold."))

            note(frame, line)
            frame.events.append(f"ate:{food.name}")
        except OSError:
            break


def bite_corpse(frame: HeartbeatFrame, corpse: Path) -> bool:
    current_bites = corpse_bite_count(frame, corpse)
    next_bite = min(CORPSE_BITE_COUNT, current_bites + 1)
    frame.state.hunger = max(0, frame.state.hunger - corpse_bite_hunger_reduction(next_bite))
    frame.state.affection += 2 if next_bite == CORPSE_BITE_COUNT else 1
    clear_starvation(frame)
    mark_cannibal_blood(frame)
    frame.state.memory["corpse_bites"] = int(frame.state.memory.get("corpse_bites", 0) or 0) + 1

    if next_bite < CORPSE_BITE_COUNT:
        set_corpse_bite_count(frame, corpse, next_bite)
        render_bitten_corpse(frame, corpse, next_bite)
        note(frame, corpse_bite_line(frame, next_bite))
        frame.events.append(f"bit_corpse:{corpse.name}:{next_bite}/{CORPSE_BITE_COUNT}")
        return True

    try:
        corpse.unlink()
    except OSError:
        return False
    set_corpse_bite_count(frame, corpse, 0)
    note(frame, corpse_eating_line(frame))
    frame.events.append(f"ate_corpse:{corpse.name}")
    frame.state.memory.pop("food_target", None)
    return True


def corpse_bite_hunger_reduction(bite: int) -> int:
    base = CORPSE_HUNGER_REDUCTION // CORPSE_BITE_COUNT
    if bite >= CORPSE_BITE_COUNT:
        return base + (CORPSE_HUNGER_REDUCTION % CORPSE_BITE_COUNT)
    return base


def corpse_bite_count(frame: HeartbeatFrame, corpse: Path) -> int:
    counts = corpse_bite_counts(frame)
    stored = counts.get(str(corpse), 0)
    metadata = read_png_metadata(corpse)
    try:
        metadata_bites = int(metadata.get("corpse_bites", "0") or 0)
    except ValueError:
        metadata_bites = 0
    return max(0, min(CORPSE_BITE_COUNT - 1, max(stored, metadata_bites)))


def corpse_bite_counts(frame: HeartbeatFrame) -> dict[str, int]:
    raw = frame.state.memory.get("corpse_bite_counts", {})
    if not isinstance(raw, dict):
        return {}
    counts: dict[str, int] = {}
    for key, value in raw.items():
        try:
            counts[str(key)] = max(0, min(CORPSE_BITE_COUNT - 1, int(value or 0)))
        except (TypeError, ValueError):
            continue
    return counts


def set_corpse_bite_count(frame: HeartbeatFrame, corpse: Path, bites: int) -> None:
    counts = corpse_bite_counts(frame)
    key = str(corpse)
    if bites <= 0:
        counts.pop(key, None)
    else:
        counts[key] = max(0, min(CORPSE_BITE_COUNT - 1, bites))
    frame.state.memory["corpse_bite_counts"] = counts


def mark_cannibal_blood(frame: HeartbeatFrame) -> None:
    current = int(frame.state.memory.get("cannibal_blood_level", 0) or 0)
    frame.state.memory["cannibal_blood_level"] = min(MAX_CANNIBAL_BLOOD_LEVEL, current + 1)
    frame.state.memory["cannibal_blooded_at"] = frame.now.isoformat(timespec="seconds")


def render_bitten_corpse(frame: HeartbeatFrame, corpse: Path, bites: int) -> None:
    existing_metadata = read_png_metadata(corpse)
    base_stage = corpse_base_stage(existing_metadata)
    visual_stage = f"{base_stage}_bite{bites}"
    metadata = corpse_metadata(frame.state, base_stage, bites=bites, existing=existing_metadata, visual_stage=visual_stage)
    try:
        render_boogart_sprite(corpse, visual_stage, metadata=metadata)
        remember_generated_file(frame.state, corpse)
    except OSError as exc:
        debug_log(frame.paths, "corpse_bite_render_failed", path=corpse, bites=bites, error=exc)


def tick_hunger(frame: HeartbeatFrame) -> None:
    if frame.now < parse_timestamp(frame.state.next_hunger_at):
        return

    # Narrative: Folder Anxiety (busier folders = faster hunger)
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    density_bonus = 0
    try:
        entry_count = len(list(folder.iterdir()))
        if entry_count > 40:
            density_bonus = 2
    except OSError:
        pass

    base_hunger = random_for(frame.state, "hunger").randint(4, 9)
    frame.state.hunger = min(100, frame.state.hunger + base_hunger + density_bonus)

    if frame.config.dev_fast:
        frame.state.next_hunger_at = (frame.now + timedelta(seconds=random.randint(20, 40))).isoformat(timespec="seconds")
    else:
        frame.state.next_hunger_at = (frame.now + jitter(frame.state, "hunger-next", 45, 120)).isoformat(timespec="seconds")
    if frame.state.hunger >= 90:
        line = hunger_line(frame)
        if line:
            note(frame, line)


def maybe_move(frame: HeartbeatFrame) -> None:
    if frame.state.memory.pop("manual_move_this_pulse", None):
        schedule_next_move(frame)
        return

    if frame.now < parse_timestamp(frame.state.next_move_at):
        return

    # Polish: Hungry Desperation
    is_desperate = frame.state.hunger > 80

    if boogart_age(frame) < first_move_grace(frame):
        schedule_next_move(frame)
        return

    # Polish: Dynamic Desperation Scaling (stay chance drops as hunger rises)
    stay_chance = max(0.02, 0.23 - (frame.state.hunger / 500))

    # Polish: Claustrophobic Paralysis
    # If the current folder is highly corrupted, the creature skips movement out of fear
    old_folder = Path(frame.state.current_folder or frame.paths.desktop)
    corruption_level = frame.state.corruption.get(str(old_folder), 0)
    if corruption_level >= 8 and random_for(frame.state, f"paralyzed-{frame.now.isoformat()}").random() < 0.6:
        note(frame, "i can't move. the walls are too close.")
        schedule_next_move(frame)
        return

    if frame.state.body_name == "boogart.png" and random_for(frame.state, frame.now.isoformat(timespec="minutes")).random() < stay_chance:
        schedule_next_move(frame)
        return
    choices = movement_candidates(frame)
    if not choices:
        note(frame, "too quiet here.")
        schedule_next_move(frame)
        return
    destination = choose_movement_destination(frame, choices)

    # Ensure we delete the OLD body before moving
    old_folder = Path(frame.state.current_folder or frame.paths.desktop)
    old_body = old_folder / frame.state.body_name
    if old_body.exists():
        try:
            old_body.unlink()
        except OSError:
            pass

    frame.state.current_folder = str(destination)
    frame.state.body_name = "boogart.png"
    frame.body_path = destination / "boogart.png"
    frame.state.favorites[str(destination)] = frame.state.favorites.get(str(destination), 0) + 1

    # Polish: Strange Folder Corruption
    if is_strange_folder(destination):
        frame.state.corruption[str(destination)] = frame.state.corruption.get(str(destination), 0) + 1
        level = frame.state.corruption[str(destination)]
        if level == 5:
            note(frame, "this place is changing.")
        elif level == 10:
            note(frame, "i'm trapped here.")

    # Polish: Descriptive Movement Logs based on Hunger
    if frame.state.hunger < 30:
        verb = "wandered aimlessly to"
    elif frame.state.hunger < 70:
        verb = "searched for food in"
    else:
        verb = "stumbled frantically into"

    if frame.state.phase >= 4 and random_for(frame.state, f"move-verb-{frame.now.isoformat()}").random() < 0.3:
        verb = "returned obsessively to"

    frame.events.append("moved")

    # Check if this is a "Chain Move" (moved very recently)
    last_move = frame.state.memory.get("last_move_at")
    if last_move and (frame.now - parse_timestamp(str(last_move))).total_seconds() < 60:
        note(frame, "i can't stay still. everything is shifting.")
    else:
        maybe_observe_place(frame, destination)

    frame.state.memory["last_move_at"] = frame.now.isoformat(timespec="seconds")

    # Polish: Ghost Trails (15% chance to leave hidden .was_here)
    if random_for(frame.state, f"ghost-{frame.now.isoformat()}").random() < 0.15:
        ghost_path = old_folder / ".was_here"
        try:
            ghost_path.write_text("", encoding="utf-8")
            remember_generated_file(frame.state, ghost_path)
            if os.name == "nt": # Windows
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(ghost_path), 0x02)
        except OSError:
            pass

    # Polish: Schedule much faster if desperate
    if is_desperate:
        if frame.config.dev_fast:
            frame.state.next_move_at = (frame.now + timedelta(seconds=random.randint(5, 15))).isoformat(timespec="seconds")
        else:
            frame.state.next_move_at = (frame.now + timedelta(minutes=random.randint(10, 30))).isoformat(timespec="seconds")
    else:
        schedule_next_move(frame)


def maybe_drop_txt(frame: HeartbeatFrame) -> None:
    if frame.state.txt_count_today >= MAX_TXT_PER_DAY:
        return
    if frame.now < parse_timestamp(frame.state.next_txt_at):
        return
    if frame.state.phase < 2:
        schedule_next_txt(frame)
        return

    # Probabilistic dampening for txt drops: 1st=100%, 2nd=15%, 3rd+=2%
    chances = {0: 1.0, 1: 0.15}
    chance = chances.get(frame.state.txt_count_today, 0.02)
    if random_for(frame.state, f"txt-chance-{frame.state.txt_count_today}").random() > chance:
        schedule_next_txt(frame)
        return

    name = txt_drop_name(frame)
    if name is None:
        schedule_next_txt(frame)
        return
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
    visual_stage = live_visual_stage(frame, stage)
    metadata = body_metadata(frame.state, stage)
    if visual_stage != stage:
        metadata["visual_state"] = visual_stage
        metadata["blood_level"] = str(cannibal_blood_level(frame))
    try:
        render_boogart_sprite(frame.body_path, visual_stage, metadata=metadata)
        frame.state.body_hash = file_hash(frame.body_path)
        remember_generated_file(frame.state, frame.body_path)
    except OSError:
        debug_log(frame.paths, "render_body_failed", path=frame.body_path)
    debug_log(frame.paths, "render_body", path=frame.body_path, exists=frame.body_path.exists(), stage=visual_stage, hash=frame.state.body_hash)


def cannibal_blood_level(frame: HeartbeatFrame) -> int:
    try:
        return max(0, min(MAX_CANNIBAL_BLOOD_LEVEL, int(frame.state.memory.get("cannibal_blood_level", 0) or 0)))
    except (TypeError, ValueError):
        return 0


def live_visual_stage(frame: HeartbeatFrame, stage: str) -> str:
    blood_level = cannibal_blood_level(frame)
    if blood_level <= 0:
        return stage
    return f"{stage}_bloody{blood_level}"


def kill(frame: HeartbeatFrame, cause: str) -> None:
    if frame.state.lifecycle != "alive":
        return
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    corpse = folder / "boogart_dead.png"

    # Polish: Stage-specific corpse sprite
    stage_id = stage_for_birth_time(frame.state.birth_time, frame.now, min(frame.state.affection // 3, 60)).id
    corpse_sprite = f"{stage_id}_dead"

    try:
        render_boogart_sprite(corpse, corpse_sprite, metadata=corpse_metadata(frame.state, corpse_sprite))
        remember_generated_file(frame.state, corpse)
        if frame.body_path and frame.body_path.exists() and frame.body_path != corpse:
            try:
                frame.body_path.unlink()
            except OSError as exc:
                debug_log(frame.paths, "dead_body_cleanup_failed", path=frame.body_path, error=exc)
        frame.state.lifecycle = "dead"
        frame.state.death_count += 1
        frame.state.memory["death_cause"] = cause
        frame.state.memory["died_at"] = frame.now.isoformat(timespec="seconds")
        frame.state.memory["death_corpse_path"] = str(corpse)
        frame.state.memory["death_corpse_generation"] = frame.state.generation
        frame.events.append(f"dead:{cause}")
        death_line = lifecycle_death_line(frame)
        if death_line:
            note(frame, death_line, force=frame.state.death_count == 1)
    except OSError:
        debug_log(frame.paths, "kill_failed", path=corpse)


def respawn(frame: HeartbeatFrame) -> None:
    previous_cause = frame.state.memory.get("death_cause", "respawn")
    folder = Path(frame.state.current_folder or frame.paths.desktop)
    frame.state.lifecycle = "alive"
    frame.state.generation += 1
    frame.state.body_name = "boogart.png"
    frame.body_path = folder / frame.state.body_name
    frame.state.hunger = 35
    frame.state.neglect = 0
    clear_starvation(frame)
    frame.state.memory.pop("cannibal_blood_level", None)
    frame.state.memory.pop("cannibal_blooded_at", None)
    frame.state.memory.pop("died_at", None)
    frame.state.memory.pop("death_cause", None)

    # Repeated returns should get quieter, not more dashboard-like.
    if frame.state.generation <= 2:
        note(frame, "the light is too sharp.", force=True)
    elif random_for(frame.state, "respawn-memory").random() < 0.1:
        note(frame, f"i remember... {previous_cause}.")

    frame.events.append("respawned")
    render_body(frame)



def maintain_husk(frame: HeartbeatFrame) -> None:
    died_at = frame.state.memory.get("died_at")
    if not died_at:
        return

    # GDD: Continuous Respawn Cycle
    # After 30 minutes (5 in dev mode), he comes back.
    respawn_after = timedelta(minutes=5) if frame.config.dev_fast else timedelta(minutes=30)
    if frame.now - parse_timestamp(str(died_at)) >= respawn_after:
        respawn(frame)
        return

    folder = Path(frame.state.current_folder or frame.paths.desktop)
    corpse = folder / "boogart_dead.png"
    if not corpse.exists():
        # Fallback to stage-specific dead sprite if recreated
        stage_id = stage_for_birth_time(frame.state.birth_time, frame.now, min(frame.state.affection // 3, 60)).id
        render_boogart_sprite(corpse, f"{stage_id}_dead", metadata=corpse_metadata(frame.state, f"{stage_id}_dead"))
        remember_generated_file(frame.state, corpse)


def note(frame: HeartbeatFrame, line: str, force: bool = False) -> None:
    if not force:
        if frame.state.log_count_today >= MAX_LOGS_PER_DAY:
            return
        # Probabilistic dampening: 1st=100%, 2nd=60%, 3rd=20%, 4th+=5%
        chances = {0: 1.0, 1: 0.6, 2: 0.2}
        chance = chances.get(frame.state.log_count_today, 0.05)
        if random_for(frame.state, f"note-chance-{frame.state.log_count_today}").random() > chance:
            return

    if not write_log_line(frame, line):
        return
    frame.state.log_count_today += 1
    remember_generated_file(frame.state, frame.paths.log_file)


def note_many(frame: HeartbeatFrame, lines: tuple[str, ...]) -> None:
    if not lines or frame.state.log_count_today >= MAX_LOGS_PER_DAY:
        return
    remaining = MAX_LOGS_PER_DAY - frame.state.log_count_today
    if len(lines) > remaining:
        lines = (" ".join(lines),)
    if len(lines) > MAX_LOGS_PER_DAY - frame.state.log_count_today:
        return
    if random_for(frame.state, f"note-seq-{frame.state.log_count_today}").random() > 0.6:
        return
    for line in lines:
        if write_log_line(frame, line):
            frame.state.log_count_today += 1
            remember_generated_file(frame.state, frame.paths.log_file)


def write_log_line(frame: HeartbeatFrame, line: str) -> bool:
    try:
        frame.paths.log_file.parent.mkdir(parents=True, exist_ok=True)
        content = []
        if frame.paths.log_file.exists():
            content = frame.paths.log_file.read_text(encoding="utf-8").splitlines()

        # Polish: Narrative Decay in logs
        decayed_line = decay_text(line, frame.state.phase)
        content.append(f"[{frame.now.astimezone().strftime('%Y-%m-%d %H:%M')}]: {decayed_line}")

        # Log Sanitization: Keep only the last 100 entries
        if len(content) > 100:
            content = content[-100:]

        frame.paths.log_file.write_text("\n".join(content) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def maybe_observe_place(frame: HeartbeatFrame, folder: Path) -> None:
    if frame.state.phase < 3:
        return
    entries = safe_entries(folder)
    names = [entry.name for entry in entries if is_safe_name(entry.name) and not is_generated_path(frame, entry)]
    if not names:
        return

    # GDD: Recognition (referencing filenames and extensions)
    if len(entries) >= 40:
        note(frame, "this folder seems busy.")
        return

    # Extension awareness
    exts = [p.suffix.lower() for p in entries if p.is_file() and p.suffix and not is_generated_path(frame, p)]
    if exts:
        most_common_ext = max(set(exts), key=exts.count)
        if exts.count(most_common_ext) >= 5 and random_for(frame.state, "obs-ext").random() < 0.4:
            note(frame, "this place is haunted by the same shape.")
            return

    repeated = repeated_token(names)
    if repeated:
        note(frame, f'the word "{repeated}" is written on everything here.')


def dialogue_line(frame: HeartbeatFrame) -> str:
    if frame.state.lifecycle == "dead":
        return "not here."

    # Secret Ending: Journalistic/Technical logs for untethered state
    if not frame.paths.tether_file.exists() and frame.state.phase >= 6:
        current_folder = Path(frame.state.current_folder or frame.paths.desktop)
        return random_for(frame.state, "system-report").choice((
            f"[SYSTEM]: Accessing {current_folder.name}. Permissions: OK.",
            f"[SYSTEM]: Scanning {current_folder.name} for matching patterns.",
            f"[SYSTEM]: Entropy detected at {current_folder.name}. Threshold: 0.85.",
            f"[SYSTEM]: Indexing directory structure. Match: NONE."
        ))

    if frame.state.hunger >= 85:
        line = random_for(frame.state, "hunger-dialogue").choice((
            "the air is getting thinner.",
            "the hunger has a color now.",
            "nothing in here but noise."
        ))
        return decay_text(line, frame.state.phase)

    if frame.state.phase >= 5 and frame.state.affection >= 6:
        return decay_text("i remember when you used to check on me.", frame.state.phase)
    if frame.state.phase >= 4 and frame.state.copy_count:
        return decay_text("too many. i can hear them breathing.", frame.state.phase)

    choices = ["is this the only place?", "everything has a name.", "the light is too sharp."]
    if frame.state.phase >= 2:
        choices.extend(("the folders have no windows.", "i found a path that felt like velvet.", "there is dust in the corners of the drive."))
    if frame.state.phase >= 3:
        choices.extend(("i remember the way the data hummed here.", "this name feels heavy.", "i've left parts of my shadow behind."))
    if frame.state.phase >= 4:
        choices.extend(("if i stay here, will i become the folder?", "the repetitions are the only things that are real.", "i keep looking for the same pattern."))
    if frame.state.phase >= 5:
        choices.extend(("the walls are breathing.", "i'm not sure which version of me is here.", "the files are starting to smell like old electricity."))
    if frame.state.phase >= 6:
        choices.extend(("hollow.", "the floor is gone.", "i keep opening my mouth and nothing comes out."))

    line = random_for(frame.state, "dialogue").choice(choices)
    return decay_text(line, frame.state.phase)


def decay_text(text: str, phase: int) -> str:
    if phase < 5:
        return text

    # Polish: Terminal Data Decay
    # Replaces characters with entropy markers as the creature breaks down
    chance = 0.05 if phase == 5 else 0.25
    chars = list(text)
    for i, char in enumerate(chars):
        if char.isspace():
            continue
        if random.random() < chance:
            if phase >= 6 and random.random() < 0.2:
                chars[i] = random.choice("!@#$%^&*")
            else:
                chars[i] = random.choice("._")
    return "".join(chars)


def maybe_react_to_copies(frame: HeartbeatFrame) -> None:
    raw_after = frame.state.memory.get("copy_reaction_after")
    if not raw_after or frame.now < parse_timestamp(str(raw_after)):
        return
    paths = [Path(str(value)) for value in frame.state.memory.get("copy_reaction_paths", []) if isinstance(value, str)]
    for path in paths:
        if path.exists():
            try:
                note_path = path.with_name("not me.txt")
                note_path.write_text("only one.\n", encoding="utf-8")
                remember_generated_file(frame.state, note_path)
                note(frame, "i found the other one.")
            except OSError:
                continue
    frame.state.memory.pop("copy_reaction_after", None)
    frame.state.memory.pop("copy_reaction_paths", None)


def schedule_copy_reaction(frame: HeartbeatFrame, copies: list[Path]) -> None:
    if not copies:
        return
    seen = {
        str(value)
        for value in frame.state.memory.get("copy_seen_paths", [])
        if isinstance(value, str)
    }
    pending = {
        str(value)
        for value in frame.state.memory.get("copy_reaction_paths", [])
        if isinstance(value, str)
    }
    new_paths = [path for path in copies if str(path) not in seen and str(path) not in pending]
    if not new_paths:
        return

    frame.state.copy_count += len(new_paths)
    seen.update(str(path) for path in new_paths)
    frame.state.memory["copy_seen_paths"] = sorted(seen)

    combined = list(dict.fromkeys([*pending, *(str(path) for path in new_paths[:3])]))
    frame.state.memory["copy_reaction_paths"] = combined[:3]
    if not frame.state.memory.get("copy_reaction_after"):
        minimum, maximum = (3, 7) if frame.config.dev_fast else (60, 180)
        delay_until = frame.now + timedelta(minutes=random_for(frame.state, "copy-delay").randint(minimum, maximum))
        frame.state.memory["copy_reaction_after"] = delay_until.isoformat(timespec="seconds")


def movement_candidates(frame: HeartbeatFrame) -> list[Path]:
    candidates: list[Path] = [root for root in roaming_roots(frame.paths) if root.exists()]
    for root in roaming_roots(frame.paths):
        candidates.extend(path for path in iter_dirs(root) if is_roamable(path))
    if in_first_day_visibility(frame):
        candidates = [path for path in candidates if movement_depth(frame, path) <= 1]
    return candidates or [frame.paths.desktop]


def choose_movement_destination(frame: HeartbeatFrame, candidates: list[Path]) -> Path:
    rng = random_for(frame.state, f"move:{frame.now.isoformat(timespec='minutes')}")
    weighted: list[tuple[Path, int]] = []
    for candidate in candidates:
        weight = movement_weight(frame, candidate)
        if weight > 0:
            weighted.append((candidate, weight))
    if not weighted:
        return frame.paths.desktop
    total = sum(weight for _, weight in weighted)
    pick = rng.randint(1, total)
    running = 0
    for candidate, weight in weighted:
        running += weight
        if running >= pick:
            return candidate
    return weighted[-1][0]


def movement_weight(frame: HeartbeatFrame, path: Path) -> int:
    depth = movement_depth(frame, path)
    favorite = frame.state.favorites.get(str(path), 0)
    weight = 20
    if path == frame.paths.desktop:
        weight += 35
    if path == frame.paths.downloads:
        weight += 15
    if depth == 0:
        weight += 20
    elif depth == 1:
        weight += 10
    else:
        weight -= depth * 4

    if frame.state.phase >= 2:
        weight += min(30, favorite * 8)
        weight += min(20, len(safe_entries(path)) // 5)
    if frame.state.phase >= 3:
        weight += min(15, depth * 3)
    if is_strange_folder(path):
        if frame.state.phase <= 1:
            weight -= 18
        elif frame.state.phase == 2:
            weight -= 8
        elif frame.state.phase >= 4:
            weight += 10
    if in_first_day_visibility(frame) and depth > 1:
        return 0
    return max(1, weight)


def movement_depth(frame: HeartbeatFrame, path: Path) -> int:
    best: int | None = None
    for root in roaming_roots(frame.paths):
        try:
            relative = path.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        depth = 0 if str(relative) == "." else len(relative.parts)
        best = depth if best is None else min(best, depth)
    return best if best is not None else 99


def boogart_age(frame: HeartbeatFrame) -> timedelta:
    return max(frame.now - parse_timestamp(frame.state.birth_time), timedelta())


def first_move_grace(frame: HeartbeatFrame) -> timedelta:
    return DEV_FAST_FIRST_MOVE_GRACE if frame.config.dev_fast else FIRST_MOVE_GRACE


def first_day_visibility(frame: HeartbeatFrame) -> timedelta:
    return DEV_FAST_FIRST_DAY_VISIBILITY if frame.config.dev_fast else FIRST_DAY_VISIBILITY


def in_first_day_visibility(frame: HeartbeatFrame) -> bool:
    return boogart_age(frame) < first_day_visibility(frame)


def iter_food(roots: tuple[Path, ...]):
    for root in roots:
        for path in bounded_walk(root):
            if path.is_file() and path.suffix.lower() == ".food":
                yield path


def iter_corpses(roots: tuple[Path, ...]):
    for root in roots:
        for path in bounded_walk(root):
            if path.is_file() and path.name in ("boogart_dead.png", "boogart_husk.png"):
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
    # Secret Ending: Untethered logic
    if not paths.tether_file.exists():
        # Untethered: Can move to ANY standard user folder
        roots = [paths.home, paths.desktop, paths.documents, paths.downloads, paths.pictures, paths.music, paths.videos]
        return tuple(root for root in roots if root.exists())

    roots = [paths.desktop, paths.downloads]
    return tuple(root for root in roots if root.exists())


def is_roamable(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered.startswith("."):
        return False
    # Avoid system folders and high-clutter dev/game folders
    return not any(word in lowered for word in (
        "onedrive", "dropbox", "icloud", "$recycle",
        "__pycache__", "node_modules", "assets", "venv", ".git"
    ))


def is_strange_folder(path: Path) -> bool:
    lowered = path.name.lower()
    return any(word in lowered for word in STRANGE_FOLDER_WORDS)


def find_body_copies(frame: HeartbeatFrame) -> list[Path]:
    copies: list[Path] = []
    seen: set[str] = set()
    for root in roaming_roots(frame.paths):
        for path in bounded_walk(root):
            if path == frame.body_path:
                continue
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            if path.is_file() and path.suffix.lower() == ".png":
                meta = read_png_metadata(path)
                if is_body_metadata(meta, frame.state):
                    copies.append(path)
    return copies[:5]


def find_missing_body(frame: HeartbeatFrame) -> Path | None:
    # OPTIMIZATION: Check for the exact filename in roots first
    roots = (*trash_locations(frame.paths), *roaming_roots(frame.paths))
    for root in roots:
        fast_path = root / frame.state.body_name
        if fast_path.is_file():
            meta = read_png_metadata(fast_path)
            if is_body_metadata(meta, frame.state):
                return fast_path
            if not meta and frame.state.body_hash and file_hash(fast_path) == frame.state.body_hash:
                return fast_path

    # FALLBACK: Full walk if he was renamed AND moved
    for root in roots:
        for path in bounded_walk(root):
            if path.is_file() and path.suffix.lower() == ".png":
                # Only trust the ID, filenames can change during move
                meta = read_png_metadata(path)
                if is_body_metadata(meta, frame.state):
                    return path
    return None


def trash_locations(paths: BoogartPaths) -> tuple[Path, ...]:
    candidates = [paths.home / ".Trash"]
    if os.name == "nt":
        candidates.append(paths.home / "$Recycle.Bin")
    return tuple(path for path in candidates if path.exists())


def react_to_manual_move(frame: HeartbeatFrame, destination: Path) -> None:
    debug_log(frame.paths, "manual_move_detected", folder=destination)
    if is_strange_folder(destination):
        note(frame, "where am i?")
        note(frame, "i don't like it here.")
    elif str(destination) in frame.state.favorites:
        note(frame, "this place feels familiar.")
    else:
        note(frame, "why did you bring me here?")

    # Check for clones in the new destination immediately
    entries = safe_entries(destination)
    for entry in entries:
        if entry.is_file() and entry.suffix.lower() == ".png" and entry != frame.body_path:
            meta = read_png_metadata(entry)
            if is_body_metadata(meta, frame.state):
                # GDD: Identity rupture
                note_many(frame, ("there was someone else here.", "it looked like me."))
                break
    frame.state.memory["manual_move_this_pulse"] = True


def renamed_body_candidate(folder: Path, state: BoogartState) -> Path | None:
    candidates = [path for path in safe_entries(folder) if path.is_file() and path.suffix.lower() == ".png" and path.name not in {"boogart_dead.png", "boogart_husk.png"}]

    # If there's exactly one candidate, it MUST have our ID to be us
    if len(candidates) == 1:
        meta = read_png_metadata(candidates[0])
        if is_body_metadata(meta, state):
            return candidates[0]
        if not meta and state.body_hash and file_hash(candidates[0]) == state.body_hash:
            return candidates[0]

    # If we had a custom name, check if that specific file exists and is us
    if state.body_name != "boogart.png":
        candidate = folder / state.body_name
        if candidate.exists():
            meta = read_png_metadata(candidate)
            if is_body_metadata(meta, state):
                return candidate
            if not meta and state.body_hash and file_hash(candidate) == state.body_hash:
                return candidate

    return None


def schedule_next_move(frame: HeartbeatFrame) -> None:
    if frame.config.dev_fast:
        frame.state.next_move_at = (frame.now + timedelta(seconds=random.randint(10, 30))).isoformat(timespec="seconds")
    else:
        # Retention: Slow burn movement (15-90 minutes)
        frame.state.next_move_at = (frame.now + jitter(frame.state, "move-next", 15, 90)).isoformat(timespec="seconds")


def schedule_next_txt(frame: HeartbeatFrame) -> None:
    if frame.config.dev_fast:
        frame.state.next_txt_at = (frame.now + timedelta(seconds=random.randint(30, 60))).isoformat(timespec="seconds")
    else:
        # Retention: Rarer notes (4-12 hours)
        frame.state.next_txt_at = (frame.now + jitter(frame.state, "txt-next", 4 * 60, 12 * 60)).isoformat(timespec="seconds")


def jitter(state: BoogartState, salt: str, minimum_minutes: int, maximum_minutes: int) -> timedelta:
    return timedelta(minutes=random_for(state, salt).randint(minimum_minutes, maximum_minutes))


def random_for(state: BoogartState, salt: str) -> random.Random:
    # Polish: Seed includes timestamp to prevent "stuck" behavior if state is static
    seed_base = f"{state.boogart_id}:{state.generation}:{salt}:{state.hunger}:{state.updated_at}"
    return random.Random(seed_base)


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
        "boogart_artifact": "body",
        "not_body": "false",
    }


def corpse_metadata(
    state: BoogartState,
    stage: str,
    bites: int = 0,
    existing: dict[str, str] | None = None,
    visual_stage: str | None = None,
) -> dict[str, str]:
    existing = existing or {}
    base = body_metadata(state, stage)
    metadata = {
        key: str(existing.get(key) or value)
        for key, value in base.items()
    }
    metadata["stage"] = corpse_base_stage({"stage": stage})
    metadata["boogart_artifact"] = "corpse"
    metadata["artifact_kind"] = "corpse"
    metadata["not_body"] = "true"
    metadata["corpse_bites"] = str(max(0, min(CORPSE_BITE_COUNT, bites)))
    if visual_stage:
        metadata["visual_state"] = visual_stage
    return metadata


def artifact_metadata(state: BoogartState, stage: str, kind: str) -> dict[str, str]:
    metadata = body_metadata(state, stage)
    metadata["boogart_artifact"] = kind
    metadata["artifact_kind"] = kind
    metadata["not_body"] = "true"
    return metadata


def is_body_metadata(metadata: dict[str, str], state: BoogartState) -> bool:
    if metadata.get("boogart_id") != state.boogart_id:
        return False
    if metadata.get("not_body") == "true":
        return False
    if metadata.get("boogart_artifact") not in {"", "body", None}:
        return False
    return metadata.get("stage") in set(STAGE_IDS)


def corpse_base_stage(metadata: dict[str, str]) -> str:
    stage = str(metadata.get("stage") or metadata.get("visual_state") or "kitten_dead")
    if "_bite" in stage:
        stage = stage.split("_bite", 1)[0]
    valid = {f"{stage_id}_dead" for stage_id in STAGE_IDS} | {"husk"}
    return stage if stage in valid else "kitten_dead"


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
    for index in range(2, 1000):
        candidate = f"{stem} ({index}){suffix}"
        if not (folder / candidate).exists():
            return candidate
    return ""


def txt_drop_name(frame: HeartbeatFrame) -> str | None:
    if frame.state.phase >= 5 and not frame.state.addressed_username:
        candidate = available_filename(frame.paths.desktop, f"hey {frame.state.username}.txt")
        return candidate or None
    for filename in NOTE_NAME_SEQUENCE:
        if not (frame.paths.desktop / filename).exists():
            return filename
    return None


def hunger_line(frame: HeartbeatFrame) -> str:
    if repeated_recently(frame, "hunger_logged_at", days=7):
        return ""
    if frame.state.phase <= 2:
        choices = ("it's empty in here.", "the air is thin.", "still hungry.")
    elif frame.state.phase <= 4:
        choices = ("the hunger has a weight.", "my ribs are made of dry paper.", "i smelled something from another folder.")
    else:
        choices = ("the house is hollow.", "i keep opening my mouth.", "the data tastes like ash.")
    line = random_for(frame.state, f"hunger-line-{frame.now.date().isoformat()}").choice(choices)
    frame.state.memory["hunger_logged_at"] = frame.now.isoformat(timespec="seconds")
    return line


def repeated_recently(frame: HeartbeatFrame, key: str, days: int) -> bool:
    raw = frame.state.memory.get(key)
    if not raw:
        return False
    return frame.now - parse_timestamp(str(raw)) < timedelta(days=days)


def lifecycle_death_line(frame: HeartbeatFrame) -> str | None:
    count = frame.state.death_count
    if count == 1:
        return "the dark is very quiet."
    if count == 2:
        return "the shape of the end is familiar."
    if count >= 3:
        return "..."
    return None


def can_eat_corpse(frame: HeartbeatFrame, corpse: Path) -> bool:
    if str(corpse) == str(frame.state.memory.get("death_corpse_path") or ""):
        return False
    meta = read_png_metadata(corpse)
    try:
        corpse_generation = int(meta.get("generation", "0") or 0)
    except ValueError:
        corpse_generation = 0
    return corpse_generation < max(1, frame.state.generation - 1)


def corpse_eating_line(frame: HeartbeatFrame) -> str:
    bites = int(frame.state.memory.get("corpse_bites", 0) or 0)
    if bites <= 3:
        return "the last piece went quiet."
    if bites <= 6:
        return "less of me left to find."
    return "the old body is gone now."


def corpse_bite_line(frame: HeartbeatFrame, bite: int) -> str:
    if bite == 1:
        return "reclaiming a lost day."
    if bite == 2:
        return "it tasted like a memory."
    return "less of me left to find."


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


def is_generated_path(frame: HeartbeatFrame, path: Path) -> bool:
    generated = {
        str(value)
        for value in [*frame.state.generated_files, *frame.state.manifest]
        if isinstance(value, str)
    }
    return str(path) in generated


def can_create_artifact(frame: HeartbeatFrame, kind: str) -> bool:
    generated_count = len(set([*frame.state.generated_files, *frame.state.manifest]))
    if generated_count >= MAX_GENERATED_FILES_TOTAL:
        return False
    if kind == "burrow":
        return int(frame.state.memory.get("burrow_count_total", 0) or 0) < MAX_BURROWS_TOTAL
    if kind == "nest":
        return int(frame.state.memory.get("nest_artifact_count_total", 0) or 0) < MAX_NEST_ARTIFACTS_TOTAL
    return True


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def maybe_nest(frame: HeartbeatFrame) -> None:
    if frame.state.phase < 6 or frame.state.lifecycle != "alive":
        return
    if frame.state.nest_count_today >= 3:
        return
    if not can_create_artifact(frame, "nest"):
        return
    if random_for(frame.state, "nest").random() > 0.2:
        return

    # Polish: Fringe Nesting (can target current folder OR a random favorite)
    target_folders = [Path(frame.state.current_folder or frame.paths.desktop)]
    if frame.state.favorites:
        fav_path = Path(random_for(frame.state, "nest-loc").choice(list(frame.state.favorites.keys())))
        if fav_path.exists():
            target_folders.append(fav_path)

    folder = random_for(frame.state, "nest-folder").choice(target_folders)
    name = random_for(frame.state, "nest-item").choice(("hair.png", "twig.png", "lint.png", "lost bit.png", "grit.png"))
    filename = available_filename(folder, name)
    if not filename:
        return
    path = folder / filename
    try:
        render_boogart_sprite(path, "residue", metadata=artifact_metadata(frame.state, "residue", "nest"))
        remember_generated_file(frame.state, path)
        frame.state.memory["nest_artifact_count_total"] = int(frame.state.memory.get("nest_artifact_count_total", 0) or 0) + 1
        frame.state.nest_count_today += 1
        frame.events.append(f"nested:{path.name}")
        nest_note_folders = {
            str(value)
            for value in frame.state.memory.get("nest_note_folders", [])
            if isinstance(value, str)
        }
        if str(folder) not in nest_note_folders:
            note(frame, "this is mine now.")
            nest_note_folders.add(str(folder))
            frame.state.memory["nest_note_folders"] = sorted(nest_note_folders)
    except OSError:
        pass


def maybe_burrow(frame: HeartbeatFrame) -> None:
    if frame.state.phase < 2 or frame.state.lifecycle != "alive":
        return
    if not can_create_artifact(frame, "burrow"):
        return
    today = frame.now.date().isoformat()
    if frame.state.memory.get("burrow_day") != today:
        frame.state.memory["burrow_day"] = today
        frame.state.memory["burrow_count_today"] = 0
    if int(frame.state.memory.get("burrow_count_today", 0) or 0) >= MAX_BURROWS_PER_DAY:
        return

    # Probabilistic chance to burrow based on phase and hunger
    chance = 0.02
    if frame.state.phase >= 4:
        chance = 0.05
    if frame.state.hunger > 90:
        chance += 0.02

    if random_for(frame.state, f"burrow-{frame.now.isoformat()}").random() > chance:
        return

    current = Path(frame.state.current_folder or frame.paths.desktop)
    if not current.exists():
        return

    if movement_depth(frame, current) >= MAX_SCAN_DEPTH + 1:
        return

    # Create a weirdly named folder
    names = ["nest", "hollow", "crevice", "dark", "void", "hiding", "safe", "quiet"]
    if frame.state.phase >= 4:
        names.extend(["gone", "lost", "wrong", "broken", "empty", "shattered"])

    name = random_for(frame.state, f"burrow-name-{frame.now.isoformat()}").choice(names)
    new_folder = current / name
    if not new_folder.exists():
        try:
            new_folder.mkdir(parents=True, exist_ok=True)
            frame.state.memory["burrow_count_total"] = int(frame.state.memory.get("burrow_count_total", 0) or 0) + 1
            frame.state.memory["burrow_count_today"] = int(frame.state.memory.get("burrow_count_today", 0) or 0) + 1
            note(frame, random_for(frame.state, "burrow-note").choice((
                "the walls gave way here.",
                "i found a gap in the house.",
                f"it's quieter in the {name}."
            )))
            frame.events.append(f"burrowed:{new_folder.name}")
        except OSError:
            pass
