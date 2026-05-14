from __future__ import annotations

from boogart.actions.dialogue import drop_dialogue_note
from boogart.content.dialogue import load_dialogue
from boogart.core.growth import stage_for_created_at
from boogart.core.lifecycle import track_generated_file
from boogart.core.log import write_log
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, save_state
from boogart.rendering.sprite import render_boogart_sprite
from boogart.runtime import HEARTBEAT_SECONDS, heartbeat
from boogart.ui.terminal import ConsoleSetupTerminal, SetupTerminal, TkUnavailableError


def install_boogart(username: str) -> BoogartState:
    paths = BoogartPaths.discover()
    paths.ensure()

    state = BoogartState.new(username=username)
    state.current_folder = str(paths.desktop)
    stage = stage_for_created_at(state.birth_at)
    state.stage = stage.id
    dialogue = load_dialogue()
    arrival_line = dialogue.choose_for_stage(
        "first_launch",
        state.stage,
        tone="cute",
        seed=f"{state.run_id}:first_launch:cute",
    )

    save_state(paths.state_file, state)
    render_boogart_sprite(paths.desktop_boogart_png, state.stage)
    track_generated_file(state, paths.desktop_boogart_png)
    note_path = drop_dialogue_note(paths.desktop, state.username, arrival_line)
    track_generated_file(state, note_path)
    track_generated_file(state, paths.log_file)
    write_log(
        paths.log_file,
        [
            "BOOGART LOG",
            "",
            f"name known: {state.username}",
            f"stage: {state.stage}",
            "status: arrived",
            "hunger: small",
            "",
            arrival_line or "boogart is here.",
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
