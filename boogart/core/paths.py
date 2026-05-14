from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoogartPaths:
    desktop: Path
    data_dir: Path
    state_file: Path
    log_file: Path
    desktop_boogart_png: Path

    @classmethod
    def discover(cls) -> "BoogartPaths":
        home = Path.home()
        desktop = Path(os.environ.get("USERPROFILE", home)) / "Desktop" if sys.platform == "win32" else home / "Desktop"

        if sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            data_dir = appdata / "Boogart"
        else:
            data_dir = home / ".boogart"

        return cls(
            desktop=desktop,
            data_dir=data_dir,
            state_file=data_dir / "state.json",
            log_file=desktop / "boogart_log.txt",
            desktop_boogart_png=desktop / "boogart.png",
        )

    def ensure(self) -> None:
        self.desktop.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
