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
BLOOD: Color = (132, 16, 24, 255)
POSE_IDS = ("idle1", "idle2", "blink", "look", "curl", "sleep", "stare", "thin")


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
    stage_id: f"{stage_id}.png"
    for stage_id in STAGE_IDS
}
STAGE_SPRITE_FILES.update({
    "residue": "bone.png",
    "husk": "husk.png",
})
for stage_id in STAGE_IDS:
    STAGE_SPRITE_FILES[f"{stage_id}_dead"] = f"{stage_id}_dead.png"
    for pose in POSE_IDS:
        STAGE_SPRITE_FILES[f"{stage_id}_{pose}"] = f"{stage_id}_{pose}.png"
    for level in range(1, 4):
        STAGE_SPRITE_FILES[f"{stage_id}_bloody{level}"] = f"{stage_id}_bloody{level}.png"
        STAGE_SPRITE_FILES[f"{stage_id}_dead_bite{level}"] = f"{stage_id}_dead_bite{level}.png"
for level in range(1, 4):
    STAGE_SPRITE_FILES[f"husk_bite{level}"] = f"husk_bite{level}.png"

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
    "B": BLOOD,
}


def sprite_asset_path(assets_dir: Path, stage: str) -> Path:
    if stage not in STAGE_SPRITE_FILES:
        raise ValueError(f"unknown sprite stage: {stage}")
    return assets_dir / STAGE_SPRITE_FILES[stage]


def sprite_asset_candidates(assets_dir: Path, stage: str) -> list[Path]:
    candidates = [sprite_asset_path(assets_dir, stage)]
    if requires_exact_asset(stage):
        return candidates

    base = base_stage_for_visual(stage)
    if base in STAGE_IDS:
        candidates.append(assets_dir / "cat.png")
    elif base.endswith("_dead") or base == "husk":
        candidates.append(assets_dir / "dead.png")
    elif base == "residue":
        candidates.append(assets_dir / "bone.png")

    deduped: list[Path] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


def requires_exact_asset(stage: str) -> bool:
    return "_bloody" in stage or "_bite" in stage or visual_pose(stage) is not None


def base_stage_for_visual(stage: str) -> str:
    if "_bloody" in stage:
        return stage.split("_bloody", 1)[0]
    if "_bite" in stage:
        return stage.split("_bite", 1)[0]
    pose = visual_pose(stage)
    if pose:
        return stage[: -(len(pose) + 1)]
    return stage


def visual_pose(stage: str) -> str | None:
    for pose in POSE_IDS:
        if stage.endswith(f"_{pose}"):
            return pose
    return None


def visual_stage_level(stage: str) -> int:
    marker = "_bloody" if "_bloody" in stage else "_bite" if "_bite" in stage else ""
    if not marker:
        return 0
    try:
        return max(1, min(3, int(stage.rsplit(marker, 1)[1])))
    except ValueError:
        return 1


def valid_sprite_stages() -> set[str]:
    return set(STAGE_SPRITE_FILES)


def default_assets_dir() -> Path:
    return Path(__file__).with_name("assets")


def render_boogart_sprite(
    path: Path,
    stage: str,
    assets_dir: Path | None = None,
    scale: int = 8,
    metadata: dict[str, str] | None = None,
) -> None:
    if stage not in valid_sprite_stages():
        raise ValueError(f"unknown sprite stage: {stage}")

    assets_dir = assets_dir or default_assets_dir()
    if assets_dir:
        for asset_path in sprite_asset_candidates(assets_dir, stage):
            if not asset_path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            copyfile(asset_path, path)
            add_png_metadata(path, metadata)
            return

    render_placeholder_boogart(path, stage=stage, scale=scale, metadata=metadata)


def render_placeholder_boogart(path: Path, stage: str = "kitten", scale: int = 8, metadata: dict[str, str] | None = None) -> None:
    sprite = STAGE_SPRITES.get(base_stage_for_visual(stage), BASE_SPRITE)
    sprite = apply_visual_pose(sprite, stage)
    sprite = apply_visual_blood(sprite, stage)

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


def apply_visual_pose(sprite: list[str], stage: str) -> list[str]:
    pose = visual_pose(stage)
    if not pose or pose == "idle1":
        return sprite
    rows = [list(row) for row in sprite]

    if pose == "idle2":
        paint_cells(rows, [(10, 4, "D"), (10, 9, "D"), (11, 4, "D"), (11, 9, "D")])
    elif pose == "blink":
        replace_cells(rows, "E", "I")
    elif pose == "look":
        replace_cells(rows, "E", "I")
        paint_cells(rows, [(6, 5, "E"), (6, 10, "E")])
    elif pose == "curl":
        paint_cells(rows, [(10, 4, "."), (10, 9, "."), (11, 4, "."), (11, 9, "."), (12, 3, "."), (12, 10, ".")])
        paint_cells(rows, [(10, 6, "F"), (10, 7, "F"), (11, 6, "D"), (11, 7, "D")])
    elif pose == "sleep":
        replace_cells(rows, "E", "I")
        paint_cells(rows, [(10, 4, "."), (10, 9, "."), (11, 4, "."), (11, 9, "."), (12, 3, "."), (12, 10, ".")])
    elif pose == "stare":
        paint_cells(rows, [(6, 4, "E"), (6, 5, "E"), (6, 9, "E"), (6, 10, "E")])
    elif pose == "thin":
        paint_cells(rows, [(5, 1, "."), (5, 12, "."), (6, 1, "."), (6, 12, "."), (7, 1, "."), (7, 12, "."), (8, 2, "."), (8, 11, ".")])

    return ["".join(row) for row in rows]


def apply_visual_blood(sprite: list[str], stage: str) -> list[str]:
    level = visual_stage_level(stage)
    if level <= 0:
        return sprite

    if "_bloody" in stage:
        coords = [
            (8, 7), (11, 4), (11, 11),
        ]
        if level >= 2:
            coords.extend([(9, 7), (12, 4), (12, 11), (13, 4), (13, 11)])
        if level >= 3:
            coords.extend([(10, 6), (10, 8), (12, 5), (12, 10), (13, 5), (13, 10)])
        return paint(sprite, coords)

    if "_bite" in stage:
        coords = [
            (8, 7), (8, 8), (9, 7),
        ]
        if level >= 2:
            coords.extend([(7, 6), (7, 7), (9, 8), (10, 7), (10, 8)])
        if level >= 3:
            coords.extend([(6, 8), (8, 6), (9, 6), (11, 7), (11, 8)])
        return paint(sprite, coords)

    return sprite


def replace_cells(rows: list[list[str]], old: str, new: str) -> None:
    for y, row in enumerate(rows):
        for x, cell in enumerate(row):
            if cell == old:
                rows[y][x] = new


def paint_cells(rows: list[list[str]], coords: list[tuple[int, int, str]]) -> None:
    for y, x, value in coords:
        if 0 <= y < len(rows) and 0 <= x < len(rows[y]):
            rows[y][x] = value


def paint(sprite: list[str], coords: list[tuple[int, int]]) -> list[str]:
    rows = [list(row) for row in sprite]
    for y, x in coords:
        if 0 <= y < len(rows) and 0 <= x < len(rows[y]):
            rows[y][x] = "B"
    return ["".join(row) for row in rows]
