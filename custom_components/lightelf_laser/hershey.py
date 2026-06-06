"""Hershey single-stroke vector font support for the LightElf laser projector.

Hershey fonts are public-domain single-stroke vector fonts (originally developed
by Dr. A. V. Hershey at the U.S. National Bureau of Standards / NIST). They are
the de-facto standard for laser/plotter text because every glyph is described as
a set of open polylines ("strokes") rather than filled outlines -- exactly what a
galvo-scanned laser wants to draw.

``.jhf`` format (one glyph per line)
------------------------------------
    cols  0..4   5-char glyph number  (right-justified; some mirrors store a
                 placeholder like ``12345`` -- we do not rely on this field)
    cols  5..7   3-char vertex count  (INCLUDES the leading left/right bearing
                 pair, so the number of drawable coordinate pairs is count-1)
    cols  8..    pairs of characters, each pair = one (x, y) coordinate where
                 ``value = ord(char) - ord('R')``.

The FIRST coordinate pair encodes the glyph's left and right horizontal bounds
(its advance/bearing) and is NOT drawn. A pair equal to ``" R"`` (space, 'R')
is a *pen-up* marker that begins a new stroke. Y increases DOWNWARD in raw
Hershey coordinates.

The bundled ``fonts/*.jhf`` files are "occidental" single-font files: exactly 96
lines, one per printable ASCII character from space (0x20) through ``~`` (0x7F).
So glyph *index* N maps to ASCII ``chr(32 + N)``. ``parse_jhf`` still keys glyphs
by their Hershey glyph number when that number is meaningful, and also records
the file order so the simple positional ASCII mapping works regardless.

Public API
----------
    parse_jhf(text_or_path)            -> dict[int, Glyph]
    load_font(name)                    -> HersheyFont   (cached)
    list_fonts()                       -> list[str]
    render_text(text, font_name, ...)  -> list[list[tuple[float, float]]]

``render_text`` output is a list of STROKES, each stroke a list of ``(x, y)``
points. Y is FLIPPED so that up is positive (projector convention), text is laid
out left-to-right, centered on ``(x, y)`` and scaled so the cap height is about
``height`` units. Each stroke is a polyline of ``[x, y]`` vertices and the whole
list is directly consumable by ``lightelf_protocol.draw_segments_command``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

Point = Tuple[float, float]
Stroke = List[Point]


@dataclass
class Glyph:
    """A single Hershey glyph in raw Hershey coordinate space (Y down).

    ``left`` / ``right`` are the horizontal bearings used for layout/advance.
    ``strokes`` are the drawable polylines (pen-up markers already applied).
    """

    number: int
    left: float
    right: float
    strokes: List[Stroke] = field(default_factory=list)

    @property
    def width(self) -> float:
        return self.right - self.left

    def vertex_count(self) -> int:
        return sum(len(s) for s in self.strokes)


@dataclass
class HersheyFont:
    """A parsed font: glyphs keyed by Hershey number plus an ASCII map."""

    name: str
    glyphs: Dict[int, Glyph]
    ascii_map: Dict[int, int]  # ASCII codepoint -> Hershey glyph number

    def glyph_for_char(self, char: str) -> Optional[Glyph]:
        number = self.ascii_map.get(ord(char))
        if number is None:
            return None
        return self.glyphs.get(number)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_HERSHEY_ORIGIN = ord("R")


def _decode_coord(char: str) -> int:
    return ord(char) - _HERSHEY_ORIGIN


def _iter_glyph_lines(text: str):
    """Yield logical glyph records from raw ``.jhf`` text.

    Most ``.jhf`` files keep one glyph per physical line, but the historical
    format allows a glyph's coordinate data to wrap onto following lines when it
    is longer than the line. We therefore read the declared vertex count and
    keep pulling characters (across newlines) until we have collected the
    expected number of coordinate pairs.
    """

    # Normalise newlines but keep them out of the coordinate stream: a record is
    # number(5) + count(3) + count*2 coordinate chars.
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        i += 1
        if not line.strip():
            continue
        # Header may be shorter than 8 if heavily trimmed; guard against it.
        if len(line) < 8:
            # Try to merge with following line(s) -- malformed, skip.
            continue
        number_field = line[0:5]
        count_field = line[5:8]
        try:
            count = int(count_field)
        except ValueError:
            continue
        try:
            number = int(number_field)
        except ValueError:
            number = -1
        needed = count * 2  # characters of coordinate data
        data = line[8:]
        # Pull more physical lines if this glyph wraps.
        while len(data) < needed and i < n:
            data += lines[i]
            i += 1
        yield number, count, data[:needed]


def parse_jhf(text_or_path: Union[str, os.PathLike]) -> Dict[int, Glyph]:
    """Parse a ``.jhf`` file (path or raw text) into ``{glyph_number: Glyph}``.

    When a file uses placeholder glyph numbers (some mirrors store ``12345`` on
    every line) the numbers collide, so the returned dict is keyed by the
    glyph's *file position* instead, guaranteeing one entry per glyph. ASCII
    mapping is handled separately in :func:`load_font`, which knows the file
    order, so this collision does not affect text rendering.
    """

    text = _read_text(text_or_path)
    glyphs: Dict[int, Glyph] = {}
    records = list(_iter_glyph_lines(text))

    # Detect placeholder numbering: if numbers are not unique/meaningful (some
    # mirrors store ``12345`` on every line), fall back to positional keys so
    # every glyph survives instead of colliding.
    numbers = [num for num, _c, _d in records]
    unique_meaningful = len(set(numbers)) == len(numbers) and all(n >= 0 for n in numbers)

    for position, (number, count, data) in enumerate(records):
        key = number if unique_meaningful else position
        glyphs[key] = _build_glyph(key, count, data)

    return glyphs


def _build_glyph(number: int, count: int, data: str) -> Glyph:
    if count <= 0 or len(data) < 2:
        return Glyph(number=number, left=0.0, right=0.0, strokes=[])

    # First pair = left/right bearing, not drawn.
    left = float(_decode_coord(data[0]))
    right = float(_decode_coord(data[1]))

    strokes: List[Stroke] = []
    current: Stroke = []
    # Remaining pairs are vertices / pen-up markers.
    for idx in range(2, len(data) - 1, 2):
        a = data[idx]
        b = data[idx + 1]
        if a == " " and b == "R":
            # Pen up: end the current stroke, start a fresh one.
            if len(current) >= 1:
                strokes.append(current)
            current = []
            continue
        current.append((float(_decode_coord(a)), float(_decode_coord(b))))
    if current:
        strokes.append(current)

    # Keep every stroke with at least one point. Single-point strokes occur for
    # dots (e.g. the period) -- the protocol layer needs >=2 points to draw, so
    # promote a lone point to a zero-length 2-point stroke so it is not lost.
    cleaned: List[Stroke] = []
    for stroke in strokes:
        if len(stroke) >= 2:
            cleaned.append(stroke)
        elif len(stroke) == 1:
            cleaned.append([stroke[0], stroke[0]])
    return Glyph(number=number, left=left, right=right, strokes=cleaned)


def _read_text(text_or_path: Union[str, os.PathLike]) -> str:
    if isinstance(text_or_path, os.PathLike):
        with open(text_or_path, "r", encoding="latin-1") as fh:
            return fh.read()
    # Heuristic: treat as a path if it looks like one and exists, else raw text.
    candidate = str(text_or_path)
    if ("\n" not in candidate) and os.path.exists(candidate):
        with open(candidate, "r", encoding="latin-1") as fh:
            return fh.read()
    return candidate


# ---------------------------------------------------------------------------
# Font discovery / loading
# ---------------------------------------------------------------------------

def _fonts_dir() -> str:
    # Support both layouts: project root (../fonts from tools/) on the dev box, and
    # a flat deploy dir (./fonts next to this module) on the Pi. Prefer whichever
    # exists; allow an explicit override via the LASER_FONTS_DIR env var.
    env = os.environ.get("LASER_FONTS_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (os.path.join(here, "fonts"), os.path.join(here, "..", "fonts")):
        if os.path.isdir(candidate):
            return os.path.normpath(candidate)
    return os.path.normpath(os.path.join(here, "fonts"))


def list_fonts() -> List[str]:
    """Return the names (without extension) of bundled ``fonts/*.jhf`` files."""
    directory = _fonts_dir()
    if not os.path.isdir(directory):
        return []
    names = []
    for entry in os.listdir(directory):
        if entry.lower().endswith(".jhf"):
            names.append(os.path.splitext(entry)[0])
    return sorted(names)


# Standard occidental ASCII order: the bundled single-font .jhf files contain
# exactly 96 glyphs, one per ASCII codepoint from space (0x20) through 0x7F.
_ASCII_FIRST = 32
_ASCII_LAST = 127


def _build_ascii_map(glyphs: Dict[int, Glyph]) -> Dict[int, int]:
    """Build an ASCII-codepoint -> glyph-number map.

    For the bundled occidental files we map by file order: the Nth glyph is
    ASCII ``32 + N``. ``parse_jhf`` inserts glyphs in file order; preserve that
    order. Some files use real Hershey glyph numbers which are not sorted in
    ASCII order, so sorting the keys scrambles rendered text.
    """

    ordered_keys = list(glyphs.keys())
    ascii_map: Dict[int, int] = {}
    for index, key in enumerate(ordered_keys):
        codepoint = _ASCII_FIRST + index
        if codepoint > _ASCII_LAST:
            break
        ascii_map[codepoint] = key
    return ascii_map


_FONT_CACHE: Dict[str, HersheyFont] = {}


def load_font(name: str) -> HersheyFont:
    """Load (and cache) a bundled font by name (with or without ``.jhf``)."""
    base = name[:-4] if name.lower().endswith(".jhf") else name
    if base in _FONT_CACHE:
        return _FONT_CACHE[base]

    path = os.path.join(_fonts_dir(), base + ".jhf")
    if not os.path.exists(path):
        available = ", ".join(list_fonts()) or "(none)"
        raise FileNotFoundError(
            f"font {name!r} not found in {_fonts_dir()!r}; available: {available}"
        )

    glyphs = parse_jhf(path)
    ascii_map = _build_ascii_map(glyphs)
    font = HersheyFont(name=base, glyphs=glyphs, ascii_map=ascii_map)
    _FONT_CACHE[base] = font
    return font


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# Hershey cap-height reference. In the Hershey roman coordinate system the
# baseline sits near y=+9 and the cap-line near y=-12, giving an uppercase cap
# height of ~21 raw units. Using a fixed reference keeps glyph proportions
# identical across fonts regardless of which characters appear in the string.
_HERSHEY_CAP_HEIGHT = 21.0


def render_text(
    text: str,
    font_name: str,
    *,
    height: float = 200.0,
    x: float = 0.0,
    y: float = 0.0,
    tracking: float = 1.0,
) -> List[List[Tuple[float, float]]]:
    """Render ``text`` in font ``font_name`` to laser strokes.

    Returns a list of strokes; each stroke is a list of ``(x, y)`` points.
    The result is laid out left-to-right, centered on ``(x, y)``, scaled so that
    the cap height is approximately ``height`` projector units, with Y FLIPPED so
    that up is positive. ``tracking`` scales the inter-character advance (1.0 =
    natural spacing). Spaces and missing glyphs are handled gracefully (a space
    advances by a sensible default; a missing glyph is skipped but still advances
    by an em-ish width so layout stays sane).
    """

    font = load_font(font_name) if isinstance(font_name, str) else font_name
    scale = float(height) / _HERSHEY_CAP_HEIGHT

    # Default advances for space / missing glyphs, in raw Hershey units.
    space_advance = 16.0

    placed: List[Stroke] = []
    pen_x = 0.0  # current left edge of the next glyph, in raw Hershey units

    for char in text:
        if char == "\n":
            # Single-line renderer: treat newline as a space.
            pen_x += space_advance * tracking
            continue

        glyph = font.glyph_for_char(char)

        if char == " " or glyph is None and char.isspace():
            pen_x += space_advance * tracking
            continue

        if glyph is None:
            # Unknown glyph: advance by a moderate width but draw nothing.
            pen_x += space_advance * tracking
            continue

        # Shift so the glyph's left bearing lines up at pen_x.
        offset = pen_x - glyph.left
        for stroke in glyph.strokes:
            placed.append([(px + offset, py) for (px, py) in stroke])

        advance = glyph.width
        if advance <= 0:
            advance = space_advance
        pen_x += advance * tracking

    if not placed:
        return []

    # Compute the overall bounding box in raw (pre-scale, Y-down) coordinates so
    # we can center the text block on (x, y).
    xs = [px for stroke in placed for (px, _py) in stroke]
    ys = [py for stroke in placed for (_px, py) in stroke]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0

    out: List[List[Tuple[float, float]]] = []
    for stroke in placed:
        mapped: List[Tuple[float, float]] = []
        for (px, py) in stroke:
            # Center, scale, and flip Y (Hershey Y is down -> projector Y is up).
            ox = (px - cx) * scale + x
            oy = -(py - cy) * scale + y
            mapped.append((ox, oy))
        out.append(mapped)
    return out


def render_text_segments(
    text: str,
    font_name: str,
    *,
    height: float = 200.0,
    x: float = 0.0,
    y: float = 0.0,
    tracking: float = 1.0,
) -> List[List[List[float]]]:
    """Same as :func:`render_text` but returns ``[[x, y], ...]`` lists.

    This is the exact shape ``lightelf_protocol.draw_segments_command`` expects
    (a list of segments where each segment is a list of ``[x, y]`` vertices).
    """
    return [[[px, py] for (px, py) in stroke]
            for stroke in render_text(text, font_name, height=height, x=x, y=y, tracking=tracking)]


def text_bounding_box(strokes: List[List[Tuple[float, float]]]):
    """Return ``(min_x, min_y, max_x, max_y)`` of a rendered stroke list."""
    xs = [px for stroke in strokes for (px, _py) in stroke]
    ys = [py for stroke in strokes for (_px, py) in stroke]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


__all__ = [
    "Glyph",
    "HersheyFont",
    "Point",
    "Stroke",
    "parse_jhf",
    "load_font",
    "list_fonts",
    "render_text",
    "render_text_segments",
    "text_bounding_box",
]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fonts = list_fonts()
    print(f"fonts dir: {_fonts_dir()}")
    print(f"available fonts ({len(fonts)}): {', '.join(fonts)}")
    print()

    for font_name in fonts:
        try:
            font = load_font(font_name)
        except Exception as exc:  # pragma: no cover
            print(f"{font_name}: FAILED to load: {exc}")
            continue

        strokes = render_text("HELLO", font_name, height=200)
        stroke_count = len(strokes)
        point_count = sum(len(s) for s in strokes)
        bbox = text_bounding_box(strokes)
        ascii_covered = len(font.ascii_map)
        print(
            f"{font_name:<12} glyphs={len(font.glyphs):>3} "
            f"ascii={ascii_covered:>3}  HELLO: strokes={stroke_count:>2} "
            f"points={point_count:>3}  "
            f"bbox=({bbox[0]:.0f},{bbox[1]:.0f})..({bbox[2]:.0f},{bbox[3]:.0f})"
        )

    # Demonstrate the segments shape used by draw_segments_command.
    if fonts:
        sample = render_text_segments("HI", fonts[0], height=200)
        print()
        print(f'render_text_segments("HI", {fonts[0]!r}): '
              f"{len(sample)} segments, "
              f"{sum(len(s) for s in sample)} points")
        print(f"  first segment: {sample[0]}")
