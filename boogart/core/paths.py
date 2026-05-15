from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BoogartPaths:
    home: Path
    desktop: Path
    documents: Path
    downloads: Path
    pictures: Path
    music: Path
    videos: Path
    data_dir: Path
    state_file: Path
    log_file: Path
    desktop_boogart_png: Path

    @classmethod
    def discover(cls) -> "BoogartPaths":
        home = Path.home()
        desktop = Path(os.environ.get("USERPROFILE", home)) / "Desktop" if sys.platform == "win32" else home / "Desktop"
        documents = home / "Documents"
        downloads = home / "Downloads"
        pictures = home / "Pictures"
        music = home / "Music"
        videos = home / "Videos"

        if sys.platform == "win32":
            appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            data_dir = appdata / "Boogart"
        else:
            data_dir = home / ".boogart"

        return cls(
            home=home,
            desktop=desktop,
            documents=documents,
            downloads=downloads,
            pictures=pictures,
            music=music,
            videos=videos,
            data_dir=data_dir,
            state_file=data_dir / "state.json",
            log_file=desktop / "log.txt",
            desktop_boogart_png=desktop / "boogart.png",
        )

    def ensure(self) -> None:
        self.desktop.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def common_home_rooms(self) -> tuple[Path, ...]:
        return tuple(
            path
            for path in (self.desktop, self.documents, self.downloads, self.pictures, self.music, self.videos)
            if path.exists()
        )
