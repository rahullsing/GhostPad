"""Generate the Ghostpad icon: a friendly ghost on a blue-violet rounded tile.

Pure standard library (no Pillow): shapes are rasterised with supersampling for
anti-aliasing and stored as PNG frames inside a multi-resolution ICO file.

Outputs ``assets/ghostpad.ico`` (app/exe icon) and ``assets/ghostpad.png``
(256 px, used by the README)::

    python tools/make_icon.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
ROOT = Path(__file__).resolve().parent.parent
OUT_ICO = ROOT / "assets" / "ghostpad.ico"
OUT_PNG = ROOT / "assets" / "ghostpad.png"

TILE_TOP = (0x5B, 0x8C, 0xFF)  # blue
TILE_BOTTOM = (0x7C, 0x4D, 0xFF)  # violet
GHOST = (0xF5, 0xF7, 0xFF)
EYES = (0x1B, 0x1D, 0x22)


RGB = tuple[float, float, float]


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> RGB:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _in_rounded_square(u: float, v: float, margin: float, radius: float) -> bool:
    lo, hi = margin + radius, 1 - margin - radius
    dx = max(lo - u, 0.0, u - hi)
    dy = max(lo - v, 0.0, v - hi)
    return dx * dx + dy * dy <= radius * radius and margin <= u <= 1 - margin and margin <= v <= 1 - margin


def _in_ghost(u: float, v: float) -> bool:
    cx, cy, r = 0.5, 0.45, 0.25
    if (u - cx) ** 2 + (v - cy) ** 2 <= r * r:
        return True
    if cx - r <= u <= cx + r and v >= cy:
        # Three scalloped "tails" along the bottom edge.
        bottom = 0.76 + 0.035 * math.cos(2 * math.pi * (u - (cx - r)) / (2 * r / 3))
        return v <= bottom
    return False


def _in_eye(u: float, v: float, small: bool) -> bool:
    # Small frames get narrower, wider-spaced eyes so they stay two distinct dots.
    rx, ry, spread = (0.04, 0.078, 0.105) if small else (0.04, 0.056, 0.085)
    return any(((u - ex) / rx) ** 2 + ((v - 0.47) / ry) ** 2 <= 1 for ex in (0.5 - spread, 0.5 + spread))


def _sample(u: float, v: float, small: bool) -> tuple[float, float, float, float]:
    if not _in_rounded_square(u, v, margin=0.03, radius=0.22):
        return (0.0, 0.0, 0.0, 0.0)
    if _in_eye(u, v, small) and _in_ghost(u, v):
        return (*EYES, 1.0)
    if _in_ghost(u, v):
        return (*GHOST, 1.0)
    color = _lerp(TILE_TOP, TILE_BOTTOM, (u + v) / 2)
    if _in_ghost(u - 0.025, v - 0.035):  # soft drop shadow
        color = (color[0] * 0.72, color[1] * 0.72, color[2] * 0.72)
    return (*color, 1.0)


def render(size: int) -> bytes:
    """Return raw RGBA rows (PNG filter byte per row) for a ``size`` px frame."""
    ss = 4 if size <= 128 else 3
    small = size <= 24
    rows = bytearray()
    for py in range(size):
        rows.append(0)
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    u = (px + (sx + 0.5) / ss) / size
                    v = (py + (sy + 0.5) / ss) / size
                    cr, cg, cb, ca = _sample(u, v, small)
                    r, g, b, a = r + cr * ca, g + cg * ca, b + cb * ca, a + ca
            n = ss * ss
            if a:
                rows += bytes((round(r / a), round(g / a), round(b / a), round(255 * a / n)))
            else:
                rows += b"\0\0\0\0"
    return bytes(rows)


def encode_png(size: int, raw: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def build_ico(frames: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = len(header) + 16 * len(frames)
    entries, blobs = b"", b""
    for size, png in frames:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    return header + entries + blobs


def main() -> None:
    frames = [(size, encode_png(size, render(size))) for size in SIZES]
    OUT_ICO.parent.mkdir(parents=True, exist_ok=True)
    OUT_ICO.write_bytes(build_ico(frames))
    OUT_PNG.write_bytes(frames[-1][1])
    print(f"Wrote {OUT_ICO.name} ({', '.join(str(s) for s in SIZES)} px) and {OUT_PNG.name}")


if __name__ == "__main__":
    main()
