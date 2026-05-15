from __future__ import annotations

import struct
import zlib
from pathlib import Path


Color = tuple[int, int, int, int]


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_rgba_png(path: Path, width: int, height: int, pixels: list[Color], text_chunks: dict[str, str] | None = None) -> None:
    if len(pixels) != width * height:
        raise ValueError("pixel count does not match image size")

    raw_rows = []
    for y in range(height):
        start = y * width
        row = pixels[start : start + width]
        raw_rows.append(b"\x00" + b"".join(bytes(pixel) for pixel in row))

    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            *[
                _chunk(b"tEXt", key.encode("latin-1", "replace") + b"\x00" + value.encode("utf-8", "replace"))
                for key, value in (text_chunks or {}).items()
            ],
            _chunk(b"IDAT", zlib.compress(b"".join(raw_rows), level=9)),
            _chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(png)
