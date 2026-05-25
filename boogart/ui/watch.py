from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState
from boogart.runtime import RuntimeConfig, run_heartbeat
from boogart.ui.terminal import mood_label, motion_label, render_live_panel


class WatchUnavailableError(RuntimeError):
    pass


class BoogartWatchWindow:
    def __init__(self, paths: BoogartPaths, config: RuntimeConfig) -> None:
        try:
            import tkinter as tk
        except ModuleNotFoundError as exc:
            raise WatchUnavailableError("Tkinter is not available in this Python install.") from exc

        self.tk: Any = tk
        self.paths = paths
        self.config = config
        self.paused = False
        self.panel_mode = False
        self.recent_events: list[str] = []
        self.photo: Any | None = None

        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            raise WatchUnavailableError("Tkinter could not open a display.") from exc
        self.root.title("BOOGART WATCH")
        self.root.geometry("360x480")
        self.root.minsize(320, 420)
        self.root.configure(bg="#070807")
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass

        self.image_label = tk.Label(self.root, bg="#070807", width=180, height=160)
        self.image_label.pack(pady=(16, 6))

        self.status_var = tk.StringVar(value="waking up")
        self.path_var = tk.StringVar(value="")
        self.stats_var = tk.StringVar(value="")

        status = tk.Label(self.root, textvariable=self.status_var, bg="#070807", fg="#d8ffd1", font=("Consolas", 13, "bold"))
        status.pack(fill="x", padx=18)
        path_label = tk.Label(self.root, textvariable=self.path_var, bg="#070807", fg="#8da58a", font=("Consolas", 9), wraplength=320, justify="center")
        path_label.pack(fill="x", padx=18, pady=(2, 8))
        stats = tk.Label(self.root, textvariable=self.stats_var, bg="#070807", fg="#c1d8bb", font=("Consolas", 10), justify="left")
        stats.pack(fill="x", padx=18)

        self.panel = tk.Text(
            self.root,
            height=10,
            bg="#020302",
            fg="#d8ffd1",
            insertbackground="#d8ffd1",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#1f2f1f",
            font=("Consolas", 9),
            padx=8,
            pady=8,
        )
        self.panel.pack(fill="both", expand=True, padx=14, pady=(10, 12))
        self.panel.configure(state="disabled")

        controls = tk.Frame(self.root, bg="#070807")
        controls.pack(fill="x", padx=14, pady=(0, 14))
        self.pause_button = tk.Button(controls, text="Pause", command=self.toggle_pause, width=8)
        self.pause_button.pack(side="left", padx=(0, 6))
        tk.Button(controls, text="Folder", command=self.open_current_folder, width=8).pack(side="left", padx=6)
        self.panel_button = tk.Button(controls, text="Panel", command=self.toggle_panel_mode, width=8)
        self.panel_button.pack(side="left", padx=6)
        tk.Button(controls, text="Quit", command=self.root.destroy, width=8).pack(side="right")

    def run(self) -> None:
        self.pulse()
        self.root.mainloop()

    def pulse(self) -> None:
        if not self.paused:
            frame = run_heartbeat(self.paths, config=self.config)
            self.recent_events.extend(event for event in frame.events if not event.startswith("state:"))
            self.recent_events = self.recent_events[-8:]
            self.refresh(frame.state)
        else:
            self.status_var.set("paused")
        interval = 1000 if self.config.dev_fast else 10_000
        self.root.after(interval, self.pulse)

    def refresh(self, state: BoogartState) -> None:
        folder = Path(state.current_folder or self.paths.desktop)
        body = folder / state.body_name
        self.status_var.set(f"{mood_label(state)} / {motion_label(state)}")
        self.path_var.set(str(folder))
        self.stats_var.set(f"hunger {state.hunger:03d}   trust {state.affection:02d}   wrongness {state.phase + state.death_count // 2:02d}")
        self.refresh_image(body)
        self.write_panel(render_live_panel(self.paths, state, self.recent_events))

    def refresh_image(self, body: Path) -> None:
        if self.panel_mode:
            self.image_label.configure(image="", text="BOOGART", fg="#d8ffd1", font=("Consolas", 22, "bold"))
            return
        if not body.exists() or body.is_symlink():
            self.image_label.configure(image="", text="missing", fg="#8da58a", font=("Consolas", 14))
            return
        try:
            image = self.tk.PhotoImage(file=str(body))
            factor = max(1, (max(image.width(), image.height()) + 159) // 160)
            if factor > 1:
                image = image.subsample(factor, factor)
            self.photo = image
            self.image_label.configure(image=self.photo, text="")
        except self.tk.TclError:
            self.image_label.configure(image="", text=body.name, fg="#8da58a", font=("Consolas", 14))

    def write_panel(self, text: str) -> None:
        self.panel.configure(state="normal")
        self.panel.delete("1.0", "end")
        self.panel.insert("1.0", text)
        self.panel.configure(state="disabled")

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.configure(text="Resume" if self.paused else "Pause")

    def toggle_panel_mode(self) -> None:
        self.panel_mode = not self.panel_mode
        self.panel_button.configure(text="Body" if self.panel_mode else "Panel")
        if self.panel_mode:
            self.root.geometry("360x330")
            self.image_label.configure(image="", text="", height=1)
        else:
            self.root.geometry("360x480")
            self.image_label.configure(width=180, height=160)
            self.refresh_image(Path(self.path_var.get()) / "boogart.png")

    def open_current_folder(self) -> None:
        folder = Path(self.path_var.get() or self.paths.desktop)
        open_folder(folder)


def run_watch_window(paths: BoogartPaths, config: RuntimeConfig | None = None) -> None:
    BoogartWatchWindow(paths, config or RuntimeConfig.from_env()).run()


def open_folder(path: Path) -> None:
    folder = path if path.is_dir() else path.parent
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError:
        return
