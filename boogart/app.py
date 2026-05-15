from __future__ import annotations

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, remember_generated_file, save_state
from boogart.runtime import HEARTBEAT_SECONDS, body_metadata, file_hash
from boogart.rendering.sprite import render_boogart_sprite
from boogart.runtime import heartbeat
from boogart.ui.terminal import ConsoleSetupTerminal, SetupTerminal, TkUnavailableError


def install_boogart(username: str) -> BoogartState:
    paths = BoogartPaths.discover()
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
