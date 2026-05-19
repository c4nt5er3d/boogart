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


def add_png_metadata(path: Path, text_chunks: dict[str, str] | None = None) -> None:
    if not text_chunks:
        return
    try:
        data = path.read_bytes()
    except OSError:
        return
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return

    insert_at = data.find(b"IDAT") - 4
    if insert_at < 8:
        return
    chunks = b"".join(
        _chunk(b"tEXt", key.encode("latin-1", "replace") + b"\x00" + value.encode("utf-8", "replace"))
        for key, value in text_chunks.items()
    )
    path.write_bytes(data[:insert_at] + chunks + data[insert_at:])


def read_png_metadata(path: Path) -> dict[str, str]:
    try:
        data = path.read_bytes()
    except OSError:
        return {}

    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return {}

    metadata = {}
    offset = 8
    while offset + 8 < len(data):
        length, kind = struct.unpack(">I4s", data[offset : offset + 8])
        offset += 8
        if kind == b"tEXt":
            chunk_data = data[offset : offset + length]
            if b"\x00" in chunk_data:
                key, value = chunk_data.split(b"\x00", 1)
                metadata[key.decode("latin-1", "replace")] = value.decode("utf-8", "replace")
        elif kind == b"IEND":
            break
        offset += length + 4
    return metadata
