from __future__ import annotations

from collections.abc import Callable
from typing import Any


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
