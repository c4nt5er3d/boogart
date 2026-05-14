from __future__ import annotations

from pathlib import Path
from shutil import copyfile

from boogart.core.growth import STAGE_IDS
from boogart.rendering.png import Color, write_rgba_png


TRANSPARENT: Color = (0, 0, 0, 0)
INK: Color = (34, 28, 25, 255)
FUR: Color = (238, 190, 117, 255)
DARK_FUR: Color = (196, 126, 70, 255)
EAR: Color = (241, 151, 151, 255)
EYE: Color = (33, 41, 44, 255)


BASE_SPRITE = [
    "................",
    "................",
    "...I......I.....",
    "..IFI....IFI....",
    "..IFFFIIFFFFI...",
    ".IFFFFFFFFFFI...",
    ".IFFEFFFFEFFI...",
    ".IFFFFFFFFFFI...",
    "..IFFFI.IFFI....",
    "...IFFFFFFI.....",
    "....IIIIII......",
    "....IF..FI......",
    "...II....II.....",
    "................",
    "................",
    "................",
]

STAGE_SPRITE_FILES: dict[str, str] = {
    "newborn": "boogart_01_newborn.png",
    "baby_kitten": "boogart_02_baby_kitten.png",
    "kitten": "boogart_03_kitten.png",
    "young_cat": "boogart_04_young_cat.png",
    "cat": "boogart_05_cat.png",
    "first_shift": "boogart_06_first_shift.png",
    "changed": "boogart_07_changed.png",
    "final": "boogart_08_final.png",
}

STAGE_SPRITES: dict[str, list[str]] = {
    "newborn": [
        "................",
        "................",
        "................",
        "................",
        ".....IIII.......",
        "....IFFFFI......",
        "...IFFFFFEI.....",
        "...IFFFFFFI.....",
        "....IFFFFI......",
        ".....IIII.......",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    "baby_kitten": [
        "................",
        "................",
        "....I....I......",
        "...IFI..IFI.....",
        "...IFFFFFI......",
        "..IFFFFFFFI.....",
        "..IFFEFFEFI.....",
        "..IFFFFFFFI.....",
        "...IFFFFFI......",
        "....IIIII.......",
        ".....IF.........",
        "....II..........",
        "................",
        "................",
        "................",
        "................",
    ],
    "kitten": BASE_SPRITE,
    "young_cat": [
        "................",
        "...I......I.....",
        "..IFI....IFI....",
        "..IFFFIIFFFFI...",
        ".IFFFFFFFFFFI...",
        ".IFFEFFFFEFFI...",
        ".IFFFFFFFFFFI...",
        "..IFFFFFFFFI....",
        "...IFFFFFFI.....",
        "....IIIIII......",
        "....IF..FI......",
        "....IF..FI......",
        "...II....II.....",
        "................",
        "................",
        "................",
    ],
    "cat": [
        "................",
        "...I......I.....",
        "..IFI....IFI....",
        ".IIFFFIIFFFFII..",
        ".IFFFFFFFFFFFI..",
        ".IFFEFFFFEFFFI..",
        ".IFFFFFFFFFFFI..",
        "..IFFFFFFFFFI...",
        "...IFFFFFFFI....",
        "....IIIIIII.....",
        "....IF...FI.....",
        "....IF...FI.....",
        "...II.....II....",
        "................",
        "................",
        "................",
    ],
    "first_shift": [
        "................",
        "...I......I.....",
        "..IFI....IFI....",
        ".IIFFFIIFFFFII..",
        ".IFFFFFFFFFFFI..",
        ".IFFEFFFFEFFFI..",
        ".IFFFFFFFFFFFI..",
        "..IFFFFDFFFFI...",
        "...IFFFFFFFI....",
        "...DIIIIIIID....",
        "....IF...FI.....",
        "....ID...DI.....",
        "...II.....II....",
        "................",
        "................",
        "................",
    ],
    "changed": [
        "................",
        "...I......I.....",
        "..IFI....IFI....",
        ".IIFFFIIFFFFII..",
        ".IFFFFFFFFFFFI..",
        ".IFFDFFFFDFFFI..",
        ".IFFFFFFFFFFFI..",
        "..IFFFDDFFFFI...",
        "..DIFFFFFFFID...",
        "...DIIIIIIID....",
        "....ID...DI.....",
        "...DID...DID....",
        "..DII.....IID...",
        "................",
        "................",
        "................",
    ],
    "final": [
        "................",
        "..DI......ID....",
        ".DIFI....IFID...",
        ".IIFFFIIFFFFII..",
        "DIFFFFFFFFFFFID.",
        ".IFFDFFFFDFFFI..",
        ".IFFFFFFFFFFFI..",
        "D.IFFFDDFFFFI.D.",
        "..DIFFFFFFFID...",
        "...DIIIIIIID....",
        "...DID...DID....",
        "..DIID...DIID...",
        ".DII.......IID..",
        "................",
        "................",
        "................",
    ],
}

PALETTE: dict[str, Color] = {
    ".": TRANSPARENT,
    "I": INK,
    "F": FUR,
    "D": DARK_FUR,
    "E": EYE,
    "P": EAR,
}


def sprite_asset_path(assets_dir: Path, stage: str) -> Path:
    if stage not in STAGE_SPRITE_FILES:
        raise ValueError(f"unknown sprite stage: {stage}")
    return assets_dir / STAGE_SPRITE_FILES[stage]


def render_boogart_sprite(path: Path, stage: str, assets_dir: Path | None = None, scale: int = 8) -> None:
    if stage not in STAGE_IDS:
        raise ValueError(f"unknown sprite stage: {stage}")

    if assets_dir:
        asset_path = sprite_asset_path(assets_dir, stage)
        if asset_path.exists():
            copyfile(asset_path, path)
            return

    render_placeholder_boogart(path, stage=stage, scale=scale)


def render_placeholder_boogart(path: Path, stage: str = "kitten", scale: int = 8) -> None:
    sprite = STAGE_SPRITES.get(stage, BASE_SPRITE)
    width = len(sprite[0]) * scale
    height = len(sprite) * scale
    pixels: list[Color] = []

    for row in sprite:
        for _ in range(scale):
            for cell in row:
                pixels.extend([PALETTE[cell]] * scale)

    write_rgba_png(path, width, height, pixels)
