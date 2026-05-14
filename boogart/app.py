from __future__ import annotations

from boogart.core.log import write_log
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState, save_state
from boogart.rendering.sprite import render_placeholder_boogart
from boogart.ui.terminal import ConsoleSetupTerminal, SetupTerminal, TkUnavailableError


def install_boogart(username: str) -> BoogartState:
    paths = BoogartPaths.discover()
    paths.ensure()

    state = BoogartState.new(username=username)
    save_state(paths.state_file, state)
    render_placeholder_boogart(paths.desktop_boogart_png)
    write_log(
        paths.log_file,
        [
            "BOOGART LOG",
            "",
            f"name known: {state.username}",
            "status: arrived",
            "hunger: small",
            "",
            "boogart is here.",
        ],
    )
    return state


def main() -> None:
    try:
        terminal = SetupTerminal(on_complete=install_boogart)
    except TkUnavailableError:
        terminal = ConsoleSetupTerminal(on_complete=install_boogart)
    terminal.run()
