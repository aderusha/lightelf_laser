"""Build the LightElf A0 scrolling-text command from Hershey strokes.

This packet layout was reconstructed from captured Bluetooth traffic. The
scroll itself is firmware-driven: send build_a0() once plus a C0 mode-4 command
carrying run_direction + speed (built by the coordinator). The device marquees
on its own. Glyph source is our bundled Hershey fonts.

Send order matters: the A0 (text) must be sent BEFORE the C0 (mode), otherwise
the device scrolls its previously-stored text.
"""

from __future__ import annotations

from .hershey import load_font


def _x(value: float, width: int = 4) -> str:
    r = int(round(value))
    if r < 0:
        r = 0x8000 | (-r)
    return ("0000" + format(r, "x"))[-width:]


def _m(high: int, low: int) -> int:
    return ((high << 4) | (low & 0x0F)) & 0xFF


def _layout(xys, scale):
    """Calculate per-char widths, trailing pad chars, and viewport segments."""
    last = -1
    widths = []
    total = 0
    for stroke in xys:
        if last != stroke[0]:
            last = stroke[0]
            widths.append(stroke[2] * scale)
            total += stroke[2]
    pad = []
    acc = 0
    for _ in range(9):
        last += 1
        pad.append([last, [{"x": total / 2 + 100 + acc, "y": 0, "z": 0}], 200, 200])
        acc += 200
        widths.append(200 * scale)

    def wrap(ws, limit):
        run = 0
        out = []
        n = 0
        a = 0
        for i in range(len(ws)):
            if run + ws[i] <= limit:
                a += 1
                out.append([n, a])
                run += ws[i]
            else:
                c = run
                while True:
                    if c <= limit:
                        a += 1
                        out.append([n, a])
                        run = c + ws[i]
                        break
                    if c > limit and c - ws[n] < limit:
                        a += 1
                        out.append([n, a])
                        run += ws[i]
                        break
                    c -= ws[n]
                    run -= ws[n]
                    n += 1
                    a -= 1
        return out

    windows = wrap(widths, 800)
    se1 = "".join(_x(w[0], 2) for w in windows)
    se2 = "".join(_x(w[1], 2) for w in windows)
    return xys + pad, se1, se2, (-acc * scale) / 2


def _build_group(xys, time_val, feats, ver=0, solid_color=None):
    """Port of V(): geometry + per-char metadata for one text group.

    solid_color None -> cycle colors 1..7 per stroke (rainbow); otherwise draw
    every lit point in that single color index.
    """
    if not xys:
        return None
    points_total = 0
    char_count = 0
    last_char = -1
    geom = ""
    ver_hex = _x(ver, 2)
    char_points = ""
    char_widths = ""
    color = 6  # cycles 1..7 per stroke -> rainbow
    pts_in_char = 0
    time_hex = _x(int(10 * time_val) if feats.get("textDecimalTime") else int(time_val), 2)

    expanded, se1, se2, offset = _layout(xys, 0.5)
    for stroke in expanded:
        if last_char != stroke[0]:
            last_char = stroke[0]
            if char_count > 0:
                char_points += _x(pts_in_char, 2)
                pts_in_char = 0
            char_count += 1
            char_widths += _x(round(0.5 * stroke[2]), 2)
            if len(stroke[1]) > 1:
                color += 1
        if color >= 8:
            color = 1
        pts = stroke[1]
        pts_in_char += len(pts)
        for ti in range(len(pts)):
            points_total += 1
            pt = pts[ti]
            x_ = round(0.5 * pt["x"] + offset)
            y_ = round(0.5 * pt["y"])
            blank = int(pt["z"])
            col = color if solid_color is None else solid_color
            if ti == 0:
                col = 0
                blank = 1
            if ti == len(pts) - 1:
                blank = 1
            if len(pts) == 1:
                blank = int(pt["z"])
            if feats.get("textStopTime") and len(pts) > 1:
                if col == 0:
                    blank = 2
                elif (ti < len(pts) - 1 and int(pts[ti + 1].get("s", 1)) == 0) or ti == len(pts) - 1:
                    blank = 3
            if feats.get("cmdNewType"):
                geom += _x(x_) + _x(y_) + _x(col, 2) + _x(_m(0, blank), 2)
            else:
                geom += _x(x_) + _x(y_) + _x(_m(col, blank), 2)
    char_points += _x(pts_in_char, 2)
    if points_total == 0:
        return None
    return {
        "cnt": points_total,
        "charCount": char_count,
        "cmd": geom,
        "charWidthCmd": char_widths,
        "charPointCmd": char_points,
        "se1": se1,
        "se2": se2,
        "ver": ver_hex,
        "time": time_hex,
    }


def build_a0(groups, feats, ver=0, solid_color=None):
    """Port of getXysCmdArr(): assemble the full A0...A4 text command."""
    built = [
        g
        for g in (
            _build_group(grp["xys"], grp.get("time", 5), feats, ver, solid_color)
            for grp in groups
        )
        if g
    ]
    if not built:
        return ""
    total_pts = sum(g["cnt"] for g in built)
    total_chars = sum(g["charCount"] for g in built)
    s = "".join(g["cmd"] for g in built)
    k = _x(len(built), 2)
    l = "".join(_x(g["charCount"], 2) for g in built)
    p = "".join(g["charWidthCmd"] for g in built)
    d = "".join(g["charPointCmd"] for g in built)
    g1 = "".join(g["se1"] for g in built)
    g2 = "".join(g["se2"] for g in built)
    m = "".join(g["ver"] for g in built)
    j = "".join(g["time"] for g in built)
    return (
        "A0A1A2A3" + _x(total_pts) + _x(total_chars, 2) + s + k + l + p + d + g1 + g2 + m + j + "A4A5A6A7"
    ).upper()


def text_to_xys(text, font_name, unit):
    """Hershey strokes -> scroll xys: list of [charIdx, [{x,y,z,s}], width, width].

    Each Hershey stroke becomes one xys entry; multi-stroke glyphs share charIdx.
    Coordinates are in ~2x device space (the layout scales by 0.5). Y flipped (up+).
    """
    font = load_font(font_name)
    xys = []
    pen_x = 0.0
    space = 16.0
    for char_idx, ch in enumerate(text):
        glyph = font.glyph_for_char(ch)
        if ch == " " or glyph is None:
            pen_x += space
            continue
        x_off = pen_x - glyph.left
        for stroke in glyph.strokes:
            pts = [{"x": (px + x_off) * unit, "y": -py * unit, "z": 0, "s": 1} for (px, py) in stroke]
            if len(pts) >= 2:
                xys.append([char_idx, pts, glyph.width * unit, glyph.width * unit])
        pen_x += glyph.width if glyph.width > 0 else space
    # Center the text around x=0; the layout places the trailing gap/pad chars
    # at total/2 + 100 assuming this. Without
    # this, long text runs off-screen and only the first chars ever scroll in.
    half = (pen_x * unit) / 2.0
    for entry in xys:
        for pt in entry[1]:
            pt["x"] -= half
    return xys


def build_scroll_a0(text, font_name, unit, time_val=5, solid_color=None):
    """Top-level: build the A0 text command for `text`.

    solid_color None -> rainbow (cycle per stroke); otherwise a single color index.
    """
    feats = {"textStopTime": True, "cmdNewType": False, "textDecimalTime": False}
    xys = text_to_xys(text, font_name, unit)
    return build_a0([{"xys": xys, "time": time_val}], feats, ver=0, solid_color=solid_color)
