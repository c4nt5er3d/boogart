from __future__ import annotations

import argparse
from datetime import timedelta

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, remember_generated_file, save_state
from boogart.runtime import HEARTBEAT_SECONDS, RuntimeConfig, body_metadata, file_hash, heartbeat, run_simulation
from boogart.rendering.sprite import render_boogart_sprite
from boogart.ui.terminal import ConsoleSetupTerminal, SetupTerminal, TkUnavailableError


def install_boogart(username: str, paths: BoogartPaths | None = None) -> BoogartState:
    paths = paths or BoogartPaths.discover()
    paths.ensure()

    state = BoogartState.new(username=username)
    state.current_folder = str(paths.desktop)
    render_boogart_sprite(paths.desktop_boogart_png, "kitten", metadata=body_metadata(state, "kitten"))
    remember_generated_file(state, paths.desktop_boogart_png)
    state.body_hash = file_hash(paths.desktop_boogart_png)
    paths.log_file.write_text(f"[{state.created_at}]: mrrp.\n", encoding="utf-8")
    remember_generated_file(state, paths.log_file)
    state.log_count_today = 1
    state.last_log_day = state.created_at[:10]
    save_state(paths.state_file, state)
    return state


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run Boogart.")
    parser.add_argument("--dev-fast", action="store_true", help="speed up timers for local playtesting")
    parser.add_argument("--simulate", type=int, metavar="TICKS", help="run a finite heartbeat simulation and exit")
    parser.add_argument("--step-minutes", type=int, default=15, help="simulated minutes per tick")
    parser.add_argument("--once", action="store_true", help="run one heartbeat and exit")
    parser.add_argument("--name", default="friend", help="name to use for noninteractive setup")
    args = parser.parse_args(argv)

    paths = BoogartPaths.discover()
    paths.ensure()
    config = RuntimeConfig(dev_fast=args.dev_fast)

    if not paths.state_file.exists():
        if args.simulate is not None or args.once or args.dev_fast:
            install_boogart(args.name, paths)
        else:
            run_setup_terminal()

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

    run_heartbeat_loop(paths, config)


def run_setup_terminal() -> None:
    try:
        terminal = SetupTerminal(on_complete=install_boogart)
    except TkUnavailableError:
        terminal = ConsoleSetupTerminal(on_complete=install_boogart)
    terminal.run()


def run_heartbeat_loop(paths: BoogartPaths, config: RuntimeConfig | None = None) -> None:
    runtime_config = config or RuntimeConfig.from_env()
    interval_seconds = 2 if runtime_config.dev_fast else HEARTBEAT_SECONDS

    try:
        import tkinter as tk
    except ModuleNotFoundError:
        heartbeat(paths, config=runtime_config)
        return

    root = tk.Tk()
    root.withdraw()

    def pulse() -> None:
        heartbeat(paths, config=runtime_config)
        root.after(interval_seconds * 1000, pulse)

    pulse()
    root.mainloop()
