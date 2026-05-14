from __future__ import annotations

from pathlib import Path

from boogart.rendering.png import Color, write_rgba_png


TRANSPARENT: Color = (0, 0, 0, 0)
INK: Color = (34, 28, 25, 255)
FUR: Color = (238, 190, 117, 255)
DARK_FUR: Color = (196, 126, 70, 255)
EAR: Color = (241, 151, 151, 255)
EYE: Color = (33, 41, 44, 255)


SPRITE = [
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

PALETTE: dict[str, Color] = {
    ".": TRANSPARENT,
    "I": INK,
    "F": FUR,
    "D": DARK_FUR,
    "E": EYE,
    "P": EAR,
}


def render_placeholder_boogart(path: Path, scale: int = 8) -> None:
    width = len(SPRITE[0]) * scale
    height = len(SPRITE) * scale
    pixels: list[Color] = []

    for row in SPRITE:
        for _ in range(scale):
            for cell in row:
                pixels.extend([PALETTE[cell]] * scale)

    write_rgba_png(path, width, height, pixels)
