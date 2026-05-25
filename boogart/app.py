from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from contextlib import contextmanager
from datetime import timedelta
from typing import Generator

from boogart.core.debug import debug_log, debug_status
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, load_state, remember_generated_file, save_state
from boogart.runtime import HEARTBEAT_SECONDS, RuntimeConfig, body_metadata, file_hash, heartbeat, run_heartbeat, run_simulation
from boogart.rendering.sprite import render_boogart_sprite
from boogart.ui.terminal import ConsoleSetupTerminal, SetupTerminal, TkUnavailableError, render_live_panel


def install_boogart(username: str, paths: BoogartPaths | None = None) -> BoogartState:
    paths = paths or BoogartPaths.discover()
    paths.ensure()
    debug_log(paths, "install_start", username=username, desktop=paths.desktop, body=paths.desktop_boogart_png, log=paths.log_file)

    legacy_death_count = 0
    legacy_generation = 0
    legacy_lineage = []
    if paths.state_file.exists():
        try:
            old_state = load_state(paths.state_file)
            if old_state.lifecycle == "dead":
                legacy_death_count = old_state.death_count
                legacy_generation = old_state.generation
                legacy_lineage = old_state.lineage
        except (OSError, ValueError, TypeError) as exc:
            debug_log(paths, "legacy_state_load_failed", error=exc)

    state = BoogartState.new(username=username)
    state.current_folder = str(paths.desktop)

    if legacy_generation > 0:
        state.generation = legacy_generation + 1
        state.death_count = legacy_death_count
        state.lineage = legacy_lineage + [state.boogart_id]
        paths.log_file.write_text(f"[{state.created_at}]: it tasted like me.\n", encoding="utf-8")
    else:
        paths.log_file.write_text(f"[{state.created_at}]: mrrp.\n", encoding="utf-8")
        try:
            paths.tether_file.write_text("", encoding="utf-8")
            remember_generated_file(state, paths.tether_file)
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(str(paths.tether_file), 0x02) # HIDDEN
        except OSError:
            pass

    state.memory["visual_pose"] = "idle1"
    metadata = body_metadata(state, "kitten")
    metadata["visual_state"] = "kitten_idle1"
    metadata["motion"] = "idle1"
    render_boogart_sprite(paths.desktop_boogart_png, "kitten_idle1", metadata=metadata)
    debug_log(paths, "install_render_body", path=paths.desktop_boogart_png, exists=paths.desktop_boogart_png.exists(), hash=file_hash(paths.desktop_boogart_png))
    remember_generated_file(state, paths.desktop_boogart_png)
    state.body_hash = file_hash(paths.desktop_boogart_png)
    debug_log(paths, "install_write_log", path=paths.log_file, exists=paths.log_file.exists())
    remember_generated_file(state, paths.log_file)
    state.log_count_today = 1
    state.last_log_day = state.created_at[:10]
    if not save_state(paths.state_file, state):
        debug_log(paths, "install_save_state_failed", path=paths.state_file)
    debug_log(paths, "install_save_state", path=paths.state_file, exists=paths.state_file.exists())
    return state


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Boogart.")
    parser.add_argument("--dev-fast", action="store_true", help="speed up timers for local playtesting")
    parser.add_argument("--simulate", type=int, metavar="TICKS", help="run a finite heartbeat simulation and exit")
    parser.add_argument("--step-minutes", type=int, default=15, help="simulated minutes per tick")
    parser.add_argument("--once", action="store_true", help="run one heartbeat and exit")
    parser.add_argument("--name", default="friend", help="name to use for noninteractive setup")
    parser.add_argument("--sandbox", type=Path, help="run in an isolated directory")
    parser.add_argument("--live", action="store_true", help="show a tiny live terminal while Boogart runs")
    parser.add_argument("--background", action="store_true", help="run quietly without the watch window")
    parser.add_argument("--watch", action="store_true", help="show the Boogart watch window (default)")
    parser.add_argument("--debug-status", action="store_true", help="print path and debug information, then exit")
    args = parser.parse_args(argv)

    paths = BoogartPaths.discover(sandbox_root=args.sandbox)
    paths.ensure()

    if args.debug_status:
        print(debug_status(paths))
        return

    with boogart_lock(paths) as locked:
        if not locked:
            print("boogart is already running.")
            sys.exit(1)

        debug_log(paths, "paths_discovered", desktop=paths.desktop, data_dir=paths.data_dir, log=paths.log_file, body=paths.desktop_boogart_png)
        config = RuntimeConfig(dev_fast=args.dev_fast)

        if not paths.state_file.exists():
            if args.simulate is not None or args.once or args.dev_fast:
                install_boogart(args.name, paths)
            else:
                run_setup_terminal(paths)

        if args.simulate is not None:
            result = run_simulation(
                paths,
                ticks=args.simulate,
                step=timedelta(minutes=max(1, args.step_minutes)),
                config=RuntimeConfig(dev_fast=True),
            )
            print(f"ticks: {result.ticks}")
            print(f"lifecycle: {result.lifecycle}")
            print(f"phase: {result.phase}")
            print(f"hunger: {result.hunger}")
            print(f"current_folder: {result.current_folder}")
            print("events:")
            for event in result.events:
                print(f"- {event}")
            print("desktop files:")
            for filename in result.files:
                print(f"- {filename}")
            return

        if args.once:
            print(heartbeat(paths, config=config))
            return

        if args.live:
            run_live_heartbeat_loop(paths, config)
        elif args.background:
            run_heartbeat_loop(paths, config)
        else:
            run_watch_heartbeat_loop(paths, config)


def run_setup_terminal(paths: BoogartPaths | None = None) -> None:
    target_paths = paths or BoogartPaths.discover()

    def complete(username: str) -> object:
        return install_boogart(username, target_paths)

    try:
        terminal = SetupTerminal(on_complete=complete)
    except TkUnavailableError:
        terminal = ConsoleSetupTerminal(on_complete=complete)
    terminal.run()


def run_heartbeat_loop(paths: BoogartPaths, config: RuntimeConfig | None = None) -> None:
    runtime_config = config or RuntimeConfig.from_env()
    interval_seconds = 2 if runtime_config.dev_fast else HEARTBEAT_SECONDS

    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()

        def pulse() -> None:
            heartbeat(paths, config=runtime_config)
            root.after(interval_seconds * 1000, pulse)

        pulse()
        root.mainloop()
    except (ModuleNotFoundError, tk.TclError) if "tk" in locals() else ModuleNotFoundError:
        import time
        try:
            while True:
                heartbeat(paths, config=runtime_config)
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nstopping boogart.")


def run_live_heartbeat_loop(paths: BoogartPaths, config: RuntimeConfig | None = None) -> None:
    import time

    runtime_config = config or RuntimeConfig.from_env()
    interval_seconds = 2 if runtime_config.dev_fast else HEARTBEAT_SECONDS
    recent_events: list[str] = []
    try:
        while True:
            frame = run_heartbeat(paths, config=runtime_config)
            recent_events.extend(event for event in frame.events if not event.startswith("state:"))
            recent_events = recent_events[-8:]
            print("\033[2J\033[H", end="")
            print(render_live_panel(paths, frame.state, recent_events, frame.now), flush=True)
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nstopping boogart.")


def run_watch_heartbeat_loop(paths: BoogartPaths, config: RuntimeConfig | None = None) -> None:
    try:
        from boogart.ui.watch import WatchUnavailableError, run_watch_window

        run_watch_window(paths, config or RuntimeConfig.from_env())
    except WatchUnavailableError:
        run_heartbeat_loop(paths, config)


@contextmanager
def boogart_lock(paths: BoogartPaths) -> Generator[bool, None, None]:
    try:
        fd = os.open(paths.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        try:
            yield True
        finally:
            try:
                os.unlink(paths.lock_file)
            except OSError:
                pass
    except FileExistsError:
        if stale_lock_removed(paths):
            with boogart_lock(paths) as locked:
                yield locked
            return
        yield False


def stale_lock_removed(paths: BoogartPaths) -> bool:
    try:
        raw_pid = paths.lock_file.read_text(encoding="utf-8").strip()
        pid = int(raw_pid)
    except (OSError, ValueError):
        return remove_lock(paths)
    if pid <= 0 or not pid_is_running(pid):
        return remove_lock(paths)
    return False


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def remove_lock(paths: BoogartPaths) -> bool:
    try:
        paths.lock_file.unlink()
    except FileNotFoundError:
        return True
    except OSError as exc:
        debug_log(paths, "stale_lock_remove_failed", error=exc)
        return False
    debug_log(paths, "stale_lock_removed", path=paths.lock_file)
    return True
