from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from boogart.core.paths import BoogartPaths
from boogart.core.state import BoogartState
from boogart.runtime import RuntimeConfig, call_boogart, pet_boogart, run_heartbeat
from boogart.ui.terminal import mood_label, recent_today_lines


class WatchUnavailableError(RuntimeError):
    pass


class BoogartWatchWindow:
    def __init__(
        self,
        paths: BoogartPaths,
        config: RuntimeConfig,
        qt_modules: tuple[Any, Any, Any] | None = None,
        app: Any | None = None,
    ) -> None:
        self.QtCore, self.QtGui, self.QtWidgets = qt_modules or load_qt_modules()
        self.app = app or self.ensure_app()
        self.paths = paths
        self.config = config
        self.paused = False
        self.recent_events: list[str] = []
        self.current_folder = paths.desktop

        self.window = self.QtWidgets.QWidget()
        self.window.setWindowTitle("Boogart")
        self.window.resize(360, 520)
        self.window.setMinimumSize(320, 420)
        self.window.setStyleSheet(STYLE_SHEET)
        top_hint = qt_value(self.QtCore, "WindowType", "WindowStaysOnTopHint")
        if top_hint:
            self.window.setWindowFlags(self.window.windowFlags() | top_hint)

        self.title_label = self.QtWidgets.QLabel("Boogart")
        self.title_label.setObjectName("title")
        self.status_label = self.QtWidgets.QLabel("waking up")
        self.status_label.setObjectName("status")
        self.body_label = self.QtWidgets.QLabel()
        self.body_label.setObjectName("body")
        self.body_label.setFixedSize(160, 160)
        self.body_label.setAlignment(qt_value(self.QtCore, "AlignmentFlag", "AlignCenter"))
        self.folder_label = self.QtWidgets.QLabel("")
        self.folder_label.setObjectName("path")
        self.folder_label.setWordWrap(True)
        self.folder_label.setAlignment(qt_value(self.QtCore, "AlignmentFlag", "AlignCenter"))

        self.hunger_bar = self.QtWidgets.QProgressBar()
        self.hunger_bar.setRange(0, 100)
        self.hunger_bar.setTextVisible(False)
        self.trust_bar = self.QtWidgets.QProgressBar()
        self.trust_bar.setRange(0, 100)
        self.trust_bar.setTextVisible(False)

        self.events_box = self.QtWidgets.QTextEdit()
        self.events_box.setReadOnly(True)
        self.events_box.setObjectName("events")

        self.pet_button = self.QtWidgets.QPushButton("Pet")
        self.call_button = self.QtWidgets.QPushButton("Call")
        self.folder_button = self.QtWidgets.QPushButton("Open Folder")
        self.pause_button = self.QtWidgets.QPushButton("Pause")
        self.quit_button = self.QtWidgets.QPushButton("Quit")

        self.pet_button.clicked.connect(self.pet)
        self.call_button.clicked.connect(self.call)
        self.folder_button.clicked.connect(self.open_current_folder)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.quit_button.clicked.connect(self.quit)

        self.build_layout()

        self.timer = self.QtCore.QTimer(self.window)
        self.timer.timeout.connect(self.pulse)
        self.timer.start(1000 if self.config.dev_fast else 10_000)

    def ensure_app(self) -> Any:
        app = self.QtWidgets.QApplication.instance()
        if app is not None:
            return app
        return self.QtWidgets.QApplication(sys.argv[:1])

    def build_layout(self) -> None:
        layout = self.QtWidgets.QVBoxLayout(self.window)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.body_label, 0, qt_value(self.QtCore, "AlignmentFlag", "AlignCenter"))
        layout.addWidget(self.folder_label)
        layout.addWidget(self.meter_row("hunger", self.hunger_bar))
        layout.addWidget(self.meter_row("trust", self.trust_bar))
        layout.addWidget(self.events_box, 1)

        action_row = self.QtWidgets.QHBoxLayout()
        for button in (self.pet_button, self.call_button, self.folder_button):
            action_row.addWidget(button)
        layout.addLayout(action_row)

        control_row = self.QtWidgets.QHBoxLayout()
        control_row.addWidget(self.pause_button)
        control_row.addWidget(self.quit_button)
        layout.addLayout(control_row)

    def meter_row(self, label: str, bar: Any) -> Any:
        row = self.QtWidgets.QWidget()
        layout = self.QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        text = self.QtWidgets.QLabel(label)
        text.setObjectName("meterLabel")
        layout.addWidget(text)
        layout.addWidget(bar, 1)
        return row

    def run(self) -> int:
        self.pulse()
        self.window.show()
        return int(self.app.exec())

    def pulse(self) -> None:
        if self.paused:
            self.status_label.setText("paused")
            return
        frame = run_heartbeat(self.paths, config=self.config)
        self.add_events(frame.events)
        self.refresh(frame.state, frame.now)

    def pet(self) -> None:
        result = pet_boogart(self.paths)
        self.add_events(result.events)
        self.refresh(result.state, result.now)

    def call(self) -> None:
        result = call_boogart(self.paths)
        self.add_events(result.events)
        self.refresh(result.state, result.now)

    def add_events(self, events: list[str]) -> None:
        self.recent_events.extend(event for event in events if not event.startswith("state:"))
        self.recent_events = self.recent_events[-10:]

    def refresh(self, state: BoogartState, now: datetime | None = None) -> None:
        folder = Path(state.current_folder or self.paths.desktop)
        self.current_folder = folder
        self.status_label.setText(mood_label(state))
        self.folder_label.setText(str(folder))
        self.hunger_bar.setValue(max(0, min(100, int(state.hunger))))
        self.trust_bar.setValue(max(0, min(100, int(state.affection) * 5)))
        self.refresh_image(folder / state.body_name)
        self.write_events(now or datetime.now().astimezone())

    def refresh_image(self, body: Path) -> None:
        if not body.exists() or body.is_symlink():
            self.body_label.setPixmap(self.QtGui.QPixmap())
            self.body_label.setText("missing")
            return
        pixmap = self.QtGui.QPixmap(str(body))
        if hasattr(pixmap, "isNull") and pixmap.isNull():
            self.body_label.setPixmap(self.QtGui.QPixmap())
            self.body_label.setText(body.name)
            return
        scaled = pixmap.scaled(
            self.body_label.size(),
            qt_value(self.QtCore, "AspectRatioMode", "KeepAspectRatio"),
            qt_value(self.QtCore, "TransformationMode", "SmoothTransformation"),
        )
        self.body_label.setPixmap(scaled)
        self.body_label.setText("")

    def write_events(self, now: datetime) -> None:
        lines = recent_today_lines(self.paths, now, self.recent_events)
        if not lines:
            lines = ["waiting for you"]
        self.events_box.setPlainText("\n".join(lines[-8:]))

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.setText("Resume" if self.paused else "Pause")
        if self.paused:
            self.status_label.setText("paused")
        else:
            self.pulse()

    def open_current_folder(self) -> None:
        open_folder(self.current_folder)

    def quit(self) -> None:
        self.window.close()
        if hasattr(self.app, "quit"):
            self.app.quit()


def load_qt_modules() -> tuple[Any, Any, Any]:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as exc:
        raise WatchUnavailableError("PySide6 is not installed") from exc
    return QtCore, QtGui, QtWidgets


def qt_value(QtCore: Any, group_name: str, value_name: str) -> Any:
    group = getattr(QtCore.Qt, group_name, None)
    if group is not None and hasattr(group, value_name):
        return getattr(group, value_name)
    return getattr(QtCore.Qt, value_name, 0)


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


STYLE_SHEET = """
QWidget {
    background: #f7f2e8;
    color: #2f2b24;
    font-family: Arial, Helvetica, sans-serif;
    font-size: 13px;
}
QLabel#title {
    font-size: 22px;
    font-weight: 700;
}
QLabel#status {
    color: #5d6f52;
    font-weight: 700;
}
QLabel#path {
    color: #706a60;
    font-size: 11px;
}
QLabel#body {
    background: #fffaf1;
    border: 1px solid #ded4c5;
    border-radius: 8px;
}
QLabel#meterLabel {
    min-width: 52px;
    color: #5d574d;
}
QProgressBar {
    border: 1px solid #d8ccba;
    border-radius: 5px;
    height: 10px;
    background: #eee4d5;
}
QProgressBar::chunk {
    border-radius: 4px;
    background: #6f8d60;
}
QTextEdit#events {
    border: 1px solid #ded4c5;
    border-radius: 8px;
    background: #fffaf1;
    padding: 8px;
    color: #373127;
    font-family: Consolas, Menlo, monospace;
    font-size: 11px;
}
QPushButton {
    background: #2f2b24;
    color: #fffaf1;
    border: 0;
    border-radius: 6px;
    padding: 8px 10px;
}
QPushButton:hover {
    background: #4b4438;
}
"""
