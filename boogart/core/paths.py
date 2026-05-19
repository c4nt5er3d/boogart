from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


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
    lock_file: Path
    tether_file: Path
    debug_file: Path
    log_file: Path
    desktop_boogart_png: Path

    @classmethod
    def discover(cls, sandbox_root: Path | None = None) -> "BoogartPaths":
        if sandbox_root:
            sandbox_root = sandbox_root.resolve()
            home = sandbox_root
            desktop = sandbox_root / "Desktop"
            documents = sandbox_root / "Documents"
            downloads = sandbox_root / "Downloads"
            pictures = sandbox_root / "Pictures"
            music = sandbox_root / "Music"
            videos = sandbox_root / "Videos"
            data_dir = sandbox_root / ".boogart"

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
                lock_file=data_dir / "boogart.lock",
                tether_file=home / ".boogart_tether",
                debug_file=data_dir / "debug.txt",
                log_file=desktop / "log.txt",
                desktop_boogart_png=desktop / "boogart.png",
            )

        home = Path.home()
        if sys.platform == "win32":
            desktop = windows_known_folder("Desktop") or windows_onedrive_folder("Desktop") or Path(os.environ.get("USERPROFILE", home)) / "Desktop"
            documents = windows_known_folder("Documents") or windows_onedrive_folder("Documents") or home / "Documents"
            downloads = windows_known_folder("Downloads") or home / "Downloads"
            pictures = windows_known_folder("Pictures") or windows_onedrive_folder("Pictures") or home / "Pictures"
            music = windows_known_folder("Music") or home / "Music"
            videos = windows_known_folder("Videos") or home / "Videos"
        else:
            desktop = home / "Desktop"
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
            lock_file=data_dir / "boogart.lock",
            tether_file=home / ".boogart_tether",
            debug_file=data_dir / "debug.txt",
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


WINDOWS_KNOWN_FOLDER_IDS = {
    "Desktop": UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641"),
    "Documents": UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7"),
    "Downloads": UUID("374DE290-123F-4565-9164-39C4925E467B"),
    "Pictures": UUID("33E28130-4E1E-4676-835A-98395C3BC3BB"),
    "Music": UUID("4BD8D571-6D19-48D3-BE97-422220080E43"),
    "Videos": UUID("18989B1D-99B5-455B-841C-AB7C74E4DDFC"),
}


def windows_known_folder(name: str) -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    folder_id = WINDOWS_KNOWN_FOLDER_IDS.get(name)
    if folder_id is None:
        return None

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    guid = GUID(
        folder_id.time_low,
        folder_id.time_mid,
        folder_id.time_hi_version,
        (ctypes.c_ubyte * 8).from_buffer_copy(folder_id.bytes[8:]),
    )
    path_ptr = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_ptr))
    if result != 0 or not path_ptr.value:
        return None
    try:
        return Path(path_ptr.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path_ptr)


def windows_onedrive_folder(name: str) -> Path | None:
    for key in ("OneDriveConsumer", "OneDriveCommercial", "OneDrive"):
        root = os.environ.get(key)
        if root:
            path = Path(root) / name
            if path.exists():
                return path
    return None


def debug_paths(paths: BoogartPaths) -> dict[str, str]:
    return {
        "home": str(paths.home),
        "desktop": str(paths.desktop),
        "documents": str(paths.documents),
        "downloads": str(paths.downloads),
        "data_dir": str(paths.data_dir),
        "state_file": str(paths.state_file),
        "lock_file": str(paths.lock_file),
        "debug_file": str(paths.debug_file),
        "log_file": str(paths.log_file),
        "desktop_boogart_png": str(paths.desktop_boogart_png),
    }
