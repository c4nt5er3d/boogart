from __future__ import annotations

from pathlib import Path
from shutil import copyfile

from boogart.core.growth import STAGE_IDS
from boogart.rendering.png import Color, add_png_metadata, write_rgba_png


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
    "kitten": "cat.png",
    "cat": "cat.png",
    "shifting": "cat.png",
    "wrong": "cat.png",
    "corrupt": "cat.png",
    "final": "cat.png",
    "residue": "bone.png",
    "husk": "dead.png",
}
for stage_id in STAGE_IDS:
    STAGE_SPRITE_FILES[f"{stage_id}_dead"] = "dead.png"

STAGE_SPRITES: dict[str, list[str]] = {
    "residue": [
        "................",
        "................",
        "................",
        "................",
        "................",
        ".......D........",
        "......D.D.......",
        ".......D........",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
    "kitten": BASE_SPRITE,
    "cat": [
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
    "shifting": [
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
    "wrong": [
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
    "husk": [
        "................",
        "................",
        "................",
        "................",
        "................",
        ".....DDDDDD.....",
        "....D......D....",
        "....D......D....",
        "....D......D....",
        ".....DDDDDD.....",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
    ],
}

# Auto-generate _dead variants (placeholders using base sprites)
for stage_id in STAGE_IDS:
    STAGE_SPRITES[f"{stage_id}_dead"] = STAGE_SPRITES.get(stage_id, BASE_SPRITE)

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


def default_assets_dir() -> Path:
    return Path(__file__).with_name("assets")


def render_boogart_sprite(
    path: Path,
    stage: str,
    assets_dir: Path | None = None,
    scale: int = 8,
    metadata: dict[str, str] | None = None,
) -> None:
    valid_stages = list(STAGE_IDS) + ["residue", "husk"]
    for s_id in STAGE_IDS:
        valid_stages.append(f"{s_id}_dead")

    if stage not in valid_stages:
        raise ValueError(f"unknown sprite stage: {stage}")

    assets_dir = assets_dir or default_assets_dir()
    if assets_dir:
        asset_path = sprite_asset_path(assets_dir, stage)
        if asset_path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            copyfile(asset_path, path)
            add_png_metadata(path, metadata)
            return

    render_placeholder_boogart(path, stage=stage, scale=scale, metadata=metadata)


def render_placeholder_boogart(path: Path, stage: str = "kitten", scale: int = 8, metadata: dict[str, str] | None = None) -> None:
    sprite = STAGE_SPRITES.get(stage, BASE_SPRITE)

    # Scale down residue to be tiny (2x instead of 8x)
    actual_scale = 2 if stage == "residue" else scale
    width = len(sprite[0]) * actual_scale
    height = len(sprite) * actual_scale
    pixels: list[Color] = []

    for row in sprite:
        for _ in range(actual_scale):
            for cell in row:
                pixels.extend([PALETTE[cell]] * actual_scale)

    write_rgba_png(path, width, height, pixels, text_chunks=metadata)
