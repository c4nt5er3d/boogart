from __future__ import annotations

from boogart.core.growth import stage_for_created_at
from boogart.core.lifecycle import track_generated_file
from boogart.core.log import write_log
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, save_state
from boogart.rendering.sprite import render_boogart_sprite
from boogart.runtime import HEARTBEAT_SECONDS, heartbeat
from boogart.ui.terminal import ConsoleSetupTerminal, SetupTerminal, TkUnavailableError


def install_boogart(username: str, wander_scope: str = "desktop") -> BoogartState:
    paths = BoogartPaths.discover()
    paths.ensure()

    state = BoogartState.new(username=username)
    state.current_folder = str(paths.desktop)
    state.wander_scope = wander_scope if wander_scope in {"desktop", "marked", "home_rooms"} else "desktop"
    stage = stage_for_created_at(state.birth_at)
    state.stage = stage.id
    state.memory["message_cooldowns"] = {
        "vocalize": state.created_at,
        "watcher": state.created_at,
    }

    save_state(paths.state_file, state)
    render_boogart_sprite(paths.desktop_boogart_png, state.stage)
    track_generated_file(state, paths.desktop_boogart_png)
    track_generated_file(state, paths.log_file)
    write_log(
        paths.log_file,
        [
            "BOOGART LOG",
            "",
            f"stage: {state.stage}",
            "status: present",
        ],
    )
    save_state(paths.state_file, state)
    return state


def main() -> None:
    paths = BoogartPaths.discover()
    paths.ensure()

    if not paths.state_file.exists():
        try:
            terminal = SetupTerminal(on_complete=install_boogart)
        except TkUnavailableError:
            terminal = ConsoleSetupTerminal(on_complete=install_boogart)
        terminal.run()

    run_heartbeat_loop(paths)


def run_heartbeat_loop(paths: BoogartPaths) -> None:
    try:
        import tkinter as tk
    except ModuleNotFoundError:
        heartbeat(paths)
        return

    root = tk.Tk()
    root.withdraw()

    def pulse() -> None:
        heartbeat(paths)
        root.after(HEARTBEAT_SECONDS * 1000, pulse)

    pulse()
    root.mainloop()
