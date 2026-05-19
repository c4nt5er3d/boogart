from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from boogart.core.growth import parse_timestamp
from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState


INTRO_TEXT = """\
> BOOGART SETUP

Boogart is a small desktop companion that lives
on your file system. It moves between folders,
gets hungry, and leaves notes. Feed it by dropping
a .food file anywhere on your desktop.

Boogart can see your filenames. It will not read,
modify, or delete anything.

Press any key to continue. _"""


class TkUnavailableError(RuntimeError):
    pass


class SetupTerminal:
    def __init__(self, on_complete: Callable[[str], object]) -> None:
        try:
            import tkinter as tk
        except ModuleNotFoundError as exc:
            raise TkUnavailableError("Tkinter is not available in this Python install.") from exc

        self.tk: Any = tk
        self.on_complete = on_complete
        self.root = tk.Tk()
        self.root.title("BOOGART SETUP")
        self.root.geometry("720x420")
        self.root.configure(bg="#050505")
        self.root.resizable(False, False)

        self.text = tk.Text(
            self.root,
            bg="#050505",
            fg="#d8ffd1",
            insertbackground="#d8ffd1",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 16),
            padx=28,
            pady=28,
            wrap="word",
        )
        self.text.pack(fill="both", expand=True)
        self.text.insert("1.0", INTRO_TEXT)
        self.text.configure(state="disabled")

        self.name_var = tk.StringVar()
        self.name_entry: tk.Entry | None = None
        self.username = "friend"
        self.waiting_for_name = False
        self.root.bind("<Key>", self._continue_to_name)

    def run(self) -> None:
        self.root.mainloop()

    def _continue_to_name(self, _event: tk.Event) -> None:
        if self.waiting_for_name:
            return

        self.waiting_for_name = True
        self.root.unbind("<Key>")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert(
            "1.0",
            "> BOOGART SETUP\n\nwhat should boogart call you?\n\n> ",
        )

        self.name_entry = self.tk.Entry(
            self.root,
            textvariable=self.name_var,
            bg="#050505",
            fg="#d8ffd1",
            insertbackground="#d8ffd1",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 16),
        )
        self.text.window_create("end", window=self.name_entry)
        self.text.configure(state="disabled")
        self.name_entry.focus_set()
        self.name_entry.bind("<Return>", self._finish)

    def _finish(self, _event: tk.Event) -> None:
        username = self.name_var.get().strip() or "friend"
        self.username = username
        self.on_complete(self.username)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", f"> BOOGART SETUP\n\nhello, {username}.\n\ndone.\n")
        self.text.configure(state="disabled")
        self.root.after(900, self.root.destroy)


class ConsoleSetupTerminal:
    def __init__(self, on_complete: Callable[[str], object]) -> None:
        self.on_complete = on_complete

    def run(self) -> None:
        print(INTRO_TEXT)
        input()
        username = input("> BOOGART SETUP\n\nwhat should boogart call you?\n\n> ").strip()
        self.on_complete(username or "friend")
        print("\ndone.")


def render_live_panel(paths: BoogartPaths, state: BoogartState, events: list[str] | None = None, now: datetime | None = None) -> str:
    current_time = now or datetime.now().astimezone()
    today_lines = recent_today_lines(paths, current_time, events or [])
    while len(today_lines) < 6:
        today_lines.append("waiting for you")

    rows = [
        ("age", age_label(state, current_time)),
        ("mood", mood_label(state)),
        ("trust", meter(min(10, max(0, 3 + state.affection // 2)))),
        ("hunger", meter(round(state.hunger / 10))),
        ("wrongness", meter(min(10, max(0, state.phase + state.death_count // 2)))),
    ]
    width = 32
    lines = ["┌─ BOOGART LIVE ────────────────┐"]
    for label, value in rows:
        lines.append(f"│ {label}: {value}".ljust(width + 1) + "│")
    lines.append("├─ TODAY ───────────────────────┤")
    for line in today_lines[-6:]:
        lines.append(f"│ {line[:28]}".ljust(width + 1) + "│")
    lines.append("└────────────────────────────────┘")
    return "\n".join(lines)


def age_label(state: BoogartState, now: datetime) -> str:
    age = now - parse_timestamp(state.birth_time)
    if state.lifecycle == "dead":
        return "not moving"
    if age.days < 2:
        return "kitten-ish"
    if age.days < 6:
        return "small and certain"
    if age.days < 12:
        return "learning doors"
    if age.days < 30:
        return "not quite right"
    return "old enough"


def mood_label(state: BoogartState) -> str:
    if state.lifecycle == "dead":
        return "quiet"
    if state.hunger >= 100:
        return "hollow"
    if state.hunger >= 90:
        return "too polite"
    if state.hunger >= 70:
        return "pretending"
    if state.affection >= 6:
        return "almost trusting"
    if state.phase >= 5:
        return "listening"
    return "curious"


def meter(value: int, width: int = 10) -> str:
    filled = max(0, min(width, value))
    return "█" * filled + "░" * (width - filled)


def recent_today_lines(paths: BoogartPaths, now: datetime, events: list[str]) -> list[str]:
    lines: list[str] = []
    for event in events:
        phrase = event_phrase(event)
        if phrase:
            lines.append(f"{now.strftime('%H:%M')}  {phrase}")
    try:
        raw_lines = paths.log_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        raw_lines = []
    for raw in raw_lines[-12:]:
        phrase = log_phrase(raw)
        if phrase:
            lines.append(phrase)
    return lines[-6:]


def event_phrase(event: str) -> str:
    if event == "moved":
        return "found warm folder"
    if event.startswith("ate:"):
        return "ate offering"
    if event.startswith("txt:"):
        return f"left {event.split(':', 1)[1]}"
    if event.startswith("burrowed:"):
        return "made a little hollow"
    if event.startswith("nested:"):
        return f"left {event.split(':', 1)[1]}"
    if event.startswith("dead:starvation"):
        return "went very still"
    if event.startswith("respawned"):
        return "blinked again"
    return ""


def log_phrase(line: str) -> str:
    if "]: " not in line:
        return ""
    time_part, text = line.split("]: ", 1)
    stamp = time_part.strip("[")
    try:
        clock = parse_timestamp(stamp).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        clock = stamp[-5:] if len(stamp) >= 5 else "--:--"
    return f"{clock}  {text}"
