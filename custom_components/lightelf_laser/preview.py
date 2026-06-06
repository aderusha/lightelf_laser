"""Small PNG preview renderer for LightElf vector content."""

from __future__ import annotations

import struct
import zlib
from typing import Sequence


RGB_COLORS = {
    1: (255, 48, 48),
    2: (64, 255, 96),
    3: (72, 132, 255),
    4: (255, 240, 72),
    5: (64, 244, 255),
    6: (255, 72, 255),
    7: (255, 255, 255),
}


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def _encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start : start + stride])
    payload = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", payload)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _png_chunk(b"IEND", b"")
    )


def _set_pixel(
    pixels: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    color: tuple[int, int, int],
    radius: int,
) -> None:
    for py in range(y - radius, y + radius + 1):
        if py < 0 or py >= height:
            continue
        for px in range(x - radius, x + radius + 1):
            if px < 0 or px >= width:
                continue
            if (px - x) * (px - x) + (py - y) * (py - y) > radius * radius:
                continue
            offset = (py * width + px) * 3
            pixels[offset] = max(pixels[offset], color[0])
            pixels[offset + 1] = max(pixels[offset + 1], color[1])
            pixels[offset + 2] = max(pixels[offset + 2], color[2])


def _draw_line(
    pixels: bytearray,
    width: int,
    height: int,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    radius: int,
) -> None:
    x1, y1 = start
    x2, y2 = end
    steps = max(abs(x2 - x1), abs(y2 - y1), 1)
    for step in range(steps + 1):
        ratio = step / steps
        x = round(x1 + (x2 - x1) * ratio)
        y = round(y1 + (y2 - y1) * ratio)
        _set_pixel(pixels, width, height, x, y, color, radius)


def render_segments_png(
    segments: Sequence[Sequence[Sequence[int | float]]],
    *,
    width: int = 320,
    height: int = 320,
    padding: int = 18,
    background: tuple[int, int, int] = (4, 7, 12),
    default_color: int = 7,
) -> bytes:
    """Render colored vector segments to a compact PNG preview."""
    pixels = bytearray(background * (width * height))
    drawable = [segment for segment in segments if len(segment) >= 2]
    if not drawable:
        return _encode_png(width, height, pixels)

    xs = [float(point[0]) for segment in drawable for point in segment]
    ys = [float(point[1]) for segment in drawable for point in segment]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scale = min((width - 2 * padding) / span_x, (height - 2 * padding) / span_y)
    offset_x = (width - span_x * scale) / 2 - min_x * scale
    offset_y = (height - span_y * scale) / 2 + max_y * scale
    radius = 2 if max(width, height) >= 300 else 1

    def map_point(point: Sequence[int | float]) -> tuple[int, int]:
        x = round(float(point[0]) * scale + offset_x)
        y = round(offset_y - float(point[1]) * scale)
        return x, y

    for segment in drawable:
        raw_color = int(segment[0][2]) if len(segment[0]) >= 3 else default_color
        color_id = raw_color if raw_color > 0 else default_color
        color = RGB_COLORS.get(color_id, RGB_COLORS[default_color])
        for index in range(len(segment) - 1):
            _draw_line(
                pixels,
                width,
                height,
                map_point(segment[index]),
                map_point(segment[index + 1]),
                color,
                radius,
            )
        # Give single-point dots something visible if they ever sneak through.
        if len(segment) == 1:
            _set_pixel(pixels, width, height, *map_point(segment[0]), color, radius)

    return _encode_png(width, height, pixels)


def colorize_text_segments(
    segments: Sequence[Sequence[Sequence[int | float]]],
    color_id: int | None,
) -> list[list[list[float]]]:
    """Attach preview color ids to Hershey text segments."""
    out: list[list[list[float]]] = []
    next_color = 1
    for segment in segments:
        current = color_id or next_color
        out.append([[float(point[0]), float(point[1]), current] for point in segment])
        if color_id is None:
            next_color = 1 if next_color >= 7 else next_color + 1
    return out
