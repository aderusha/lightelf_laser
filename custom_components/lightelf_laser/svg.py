"""Minimal SVG outline flattener for LightElf draw-point commands.

This intentionally supports the stroke-only subset we need for laser outlines:
lines, circles, rectangles, and path commands M/L/H/V/C/Q/A/Z. It avoids browser or
graphics dependencies so it can run on the Raspberry Pi transport host.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import xml.etree.ElementTree as ET
from typing import Sequence

from .protocol import draw_points_command


SVG_COLOR_IDS = {
    "#ff0000": 1,
    "red": 1,
    "#00ff00": 2,
    "green": 2,
    "#0000ff": 3,
    "blue": 3,
    "#ffff00": 4,
    "yellow": 4,
    "#00ffff": 5,
    "cyan": 5,
    "#ff00ff": 6,
    "magenta": 6,
    "purple": 6,
    "#ffffff": 7,
    "white": 7,
    "#ef4444": 1,
    "#10b981": 2,
    "#3b82f6": 3,
    "#2d3748": 7,
}

COMMAND_RE = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
CSS_CLASS_RE = re.compile(r"\.([A-Za-z_][\w-]*)\s*\{([^}]*)\}", re.DOTALL)


@dataclass(frozen=True)
class SvgSegment:
    points: tuple[tuple[float, float], ...]
    color: int


@dataclass(frozen=True)
class SvgDrawing:
    segments: tuple[SvgSegment, ...]
    view_box: tuple[float, float, float, float]


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _float_attr(element: ET.Element, name: str, default: float = 0) -> float:
    return float(element.attrib.get(name, default))


def _style_attrs(style: str) -> dict[str, str]:
    attrs = {}
    for piece in style.split(";"):
        key, sep, value = piece.partition(":")
        if sep:
            attrs[key.strip()] = value.split("/*", 1)[0].strip()
    return attrs


def _class_styles(root: ET.Element) -> dict[str, dict[str, str]]:
    styles: dict[str, dict[str, str]] = {}
    for element in root.iter():
        if _tag_name(element.tag) != "style" or not element.text:
            continue
        for class_name, body in CSS_CLASS_RE.findall(element.text):
            styles[class_name] = _style_attrs(body)
    return styles


def _inherited_attr(
    element: ET.Element,
    parents: Sequence[ET.Element],
    name: str,
    class_styles: dict[str, dict[str, str]],
) -> str | None:
    for candidate in (element, *reversed(parents)):
        if name in candidate.attrib:
            return candidate.attrib[name]
        inline = _style_attrs(candidate.attrib.get("style", ""))
        if name in inline:
            return inline[name]
        for class_name in candidate.attrib.get("class", "").split():
            value = class_styles.get(class_name, {}).get(name)
            if value is not None:
                return value
    return None


def _stroke_color(
    element: ET.Element,
    parents: Sequence[ET.Element],
    default: int,
    class_styles: dict[str, dict[str, str]],
) -> int:
    raw = (_inherited_attr(element, parents, "stroke", class_styles) or "").strip().lower()
    if raw in {"", "none"}:
        return default
    if raw.startswith("rgb("):
        numbers = [int(float(item.strip())) for item in raw[4:-1].split(",")]
        raw = "#" + "".join(f"{value:02x}" for value in numbers[:3])
    return SVG_COLOR_IDS.get(raw, default)


def _view_box(root: ET.Element) -> tuple[float, float, float, float]:
    raw = root.attrib.get("viewBox")
    if raw:
        values = [float(item) for item in re.split(r"[\s,]+", raw.strip()) if item]
        if len(values) == 4:
            return values[0], values[1], values[2], values[3]
    width = float(root.attrib.get("width", 500))
    height = float(root.attrib.get("height", 500))
    return 0, 0, width, height


def circle_segments(cx: float, cy: float, r: float, color: int, samples: int) -> list[SvgSegment]:
    points = []
    for index in range(samples + 1):
        angle = 2 * math.pi * index / samples
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return [SvgSegment(tuple(points), color)]


def rect_segments(
    x: float,
    y: float,
    width: float,
    height: float,
    color: int,
) -> list[SvgSegment]:
    return [
        SvgSegment(
            ((x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)),
            color,
        )
    ]


def line_segments(element: ET.Element, color: int) -> list[SvgSegment]:
    return [
        SvgSegment(
            (
                (_float_attr(element, "x1"), _float_attr(element, "y1")),
                (_float_attr(element, "x2"), _float_attr(element, "y2")),
            ),
            color,
        )
    ]


def cubic(p0, p1, p2, p3, samples: int) -> list[tuple[float, float]]:
    points = []
    for index in range(1, samples + 1):
        t = index / samples
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def quadratic(p0, p1, p2, samples: int) -> list[tuple[float, float]]:
    points = []
    for index in range(1, samples + 1):
        t = index / samples
        mt = 1 - t
        points.append(
            (
                mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0],
                mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1],
            )
        )
    return points


def arc_points(
    p0: tuple[float, float],
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc: int,
    sweep: int,
    p1: tuple[float, float],
    samples: int,
) -> list[tuple[float, float]]:
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]

    rx = abs(rx)
    ry = abs(ry)
    phi = math.radians(x_axis_rotation % 360)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    dx = (p0[0] - p1[0]) / 2
    dy = (p0[1] - p1[1]) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy

    radii_scale = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if radii_scale > 1:
        scale = math.sqrt(radii_scale)
        rx *= scale
        ry *= scale

    numerator = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = 0 if denominator == 0 else math.sqrt(max(0, numerator / denominator))
    if large_arc == sweep:
        factor = -factor
    cxp = factor * rx * y1p / ry
    cyp = factor * -ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (p0[0] + p1[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (p0[1] + p1[1]) / 2

    def angle(u, v):
        dot = u[0] * v[0] + u[1] * v[1]
        det = u[0] * v[1] - u[1] * v[0]
        return math.atan2(det, dot)

    start_vec = ((x1p - cxp) / rx, (y1p - cyp) / ry)
    end_vec = ((-x1p - cxp) / rx, (-y1p - cyp) / ry)
    theta1 = angle((1, 0), start_vec)
    delta = angle(start_vec, end_vec)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi

    count = max(2, int(math.ceil(abs(delta) / (2 * math.pi) * samples)))
    points = []
    for index in range(1, count + 1):
        theta = theta1 + delta * index / count
        x = cos_phi * rx * math.cos(theta) - sin_phi * ry * math.sin(theta) + cx
        y = sin_phi * rx * math.cos(theta) + cos_phi * ry * math.sin(theta) + cy
        points.append((x, y))
    return points


def path_segments(d: str, color: int, curve_samples: int, arc_samples: int) -> list[SvgSegment]:
    tokens = COMMAND_RE.findall(d)
    index = 0
    command = ""
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    current_points: list[tuple[float, float]] = []
    segments: list[SvgSegment] = []

    def is_command(value: str) -> bool:
        return bool(re.match(r"^[A-Za-z]$", value))

    def number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def point(relative: bool = False) -> tuple[float, float]:
        x = number()
        y = number()
        if relative:
            return current[0] + x, current[1] + y
        return x, y

    def finish() -> None:
        nonlocal current_points
        if len(current_points) >= 2:
            segments.append(SvgSegment(tuple(current_points), color))
        current_points = []

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if not command:
            raise ValueError("path data starts without a command")
        relative = command.islower()
        op = command.upper()

        if op == "M":
            finish()
            current = point(relative)
            start = current
            current_points = [current]
            command = "l" if relative else "L"
        elif op == "L":
            while index < len(tokens) and not is_command(tokens[index]):
                current = point(relative)
                current_points.append(current)
        elif op == "H":
            while index < len(tokens) and not is_command(tokens[index]):
                x = number()
                current = (current[0] + x if relative else x, current[1])
                current_points.append(current)
        elif op == "V":
            while index < len(tokens) and not is_command(tokens[index]):
                y = number()
                current = (current[0], current[1] + y if relative else y)
                current_points.append(current)
        elif op == "C":
            while index < len(tokens) and not is_command(tokens[index]):
                p1 = point(relative)
                p2 = point(relative)
                p3 = point(relative)
                current_points.extend(cubic(current, p1, p2, p3, curve_samples))
                current = p3
        elif op == "Q":
            while index < len(tokens) and not is_command(tokens[index]):
                p1 = point(relative)
                p2 = point(relative)
                current_points.extend(quadratic(current, p1, p2, curve_samples))
                current = p2
        elif op == "A":
            while index < len(tokens) and not is_command(tokens[index]):
                rx = number()
                ry = number()
                rotation = number()
                large_arc = int(number())
                sweep = int(number())
                end = point(relative)
                current_points.extend(
                    arc_points(current, rx, ry, rotation, large_arc, sweep, end, arc_samples)
                )
                current = end
        elif op == "Z":
            current_points.append(start)
            current = start
            finish()
        else:
            raise ValueError(f"unsupported SVG path command {command!r}")

    finish()
    return segments


def read_svg(
    path: str,
    *,
    default_color: int = 7,
    circle_samples: int = 80,
    curve_samples: int = 10,
    arc_samples: int = 80,
) -> SvgDrawing:
    root = ET.parse(path).getroot()
    view_box = _view_box(root)
    class_styles = _class_styles(root)
    segments: list[SvgSegment] = []

    def walk(element: ET.Element, parents: list[ET.Element]) -> None:
        tag = _tag_name(element.tag)
        color = _stroke_color(element, parents, default_color, class_styles)
        if tag == "circle":
            segments.extend(
                circle_segments(
                    _float_attr(element, "cx"),
                    _float_attr(element, "cy"),
                    _float_attr(element, "r"),
                    color,
                    circle_samples,
                )
            )
        elif tag == "rect":
            segments.extend(
                rect_segments(
                    _float_attr(element, "x"),
                    _float_attr(element, "y"),
                    _float_attr(element, "width"),
                    _float_attr(element, "height"),
                    color,
                )
            )
        elif tag == "line":
            segments.extend(line_segments(element, color))
        elif tag == "path" and element.attrib.get("d"):
            segments.extend(path_segments(element.attrib["d"], color, curve_samples, arc_samples))

        next_parents = parents + [element]
        for child in element:
            walk(child, next_parents)

    walk(root, [])
    return SvgDrawing(tuple(segments), view_box)


def transform_segments(
    drawing: SvgDrawing,
    *,
    size: int = 640,
    x: int = 0,
    y: int = 0,
    invert_y: bool = True,
) -> list[list[list[int]]]:
    min_x, min_y, width, height = drawing.view_box
    scale = size / max(width, height)
    center_x = min_x + width / 2
    center_y = min_y + height / 2
    transformed: list[list[list[int]]] = []
    for segment in drawing.segments:
        points = []
        for sx, sy in segment.points:
            px = x + (sx - center_x) * scale
            py = (center_y - sy) * scale if invert_y else (sy - center_y) * scale
            py += y
            points.append([round(px), round(py), segment.color])
        transformed.append(points)
    return transformed


def segment_bbox_area(segment: Sequence[Sequence[int | float]]) -> float:
    xs = [float(point[0]) for point in segment]
    ys = [float(point[1]) for point in segment]
    return (max(xs) - min(xs)) * (max(ys) - min(ys))


def prepare_laser_segments(
    segments: Sequence[Sequence[Sequence[int]]],
    *,
    drop_largest: int = 0,
    largest_last: bool = False,
    color_map: dict[int, int] | None = None,
) -> list[list[list[int]]]:
    prepared = [list(list(point) for point in segment) for segment in segments]
    if color_map:
        for segment in prepared:
            for point in segment:
                point[2] = color_map.get(int(point[2]), int(point[2]))
    if drop_largest > 0:
        drop_ids = {
            index
            for index, _ in sorted(
                enumerate(prepared),
                key=lambda item: segment_bbox_area(item[1]),
                reverse=True,
            )[:drop_largest]
        }
        prepared = [segment for index, segment in enumerate(prepared) if index not in drop_ids]
    if largest_last:
        prepared = sorted(prepared, key=segment_bbox_area)
    return prepared


def _point_line_distance(
    point: Sequence[int | float],
    start: Sequence[int | float],
    end: Sequence[int | float],
) -> float:
    px, py = float(point[0]), float(point[1])
    x1, y1 = float(start[0]), float(start[1])
    x2, y2 = float(end[0]), float(end[1])
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    return abs(dy * px - dx * py + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def simplify_segment(
    segment: Sequence[Sequence[int]],
    tolerance: float,
) -> list[list[int]]:
    """Ramer-Douglas-Peucker simplification preserving a segment's endpoints."""

    points = [list(point) for point in segment]
    if tolerance <= 0 or len(points) <= 2:
        return points

    def simplify_range(start_index: int, end_index: int) -> list[list[int]]:
        if end_index <= start_index + 1:
            return [points[start_index], points[end_index]]
        max_distance = -1.0
        split_index = start_index
        for index in range(start_index + 1, end_index):
            distance = _point_line_distance(points[index], points[start_index], points[end_index])
            if distance > max_distance:
                max_distance = distance
                split_index = index
        if max_distance <= tolerance:
            return [points[start_index], points[end_index]]
        left = simplify_range(start_index, split_index)
        right = simplify_range(split_index, end_index)
        return left[:-1] + right

    is_closed = points[0][0] == points[-1][0] and points[0][1] == points[-1][1]
    if is_closed and len(points) > 4:
        farthest_index = max(
            range(1, len(points) - 1),
            key=lambda index: math.hypot(
                float(points[index][0]) - float(points[0][0]),
                float(points[index][1]) - float(points[0][1]),
            ),
        )
        left = simplify_range(0, farthest_index)
        right = simplify_range(farthest_index, len(points) - 1)
        closed = left[:-1] + right
        if closed[0] != closed[-1]:
            closed.append(closed[0])
        return closed

    return simplify_range(0, len(points) - 1)


def simplify_segments(
    segments: Sequence[Sequence[Sequence[int]]],
    tolerance: float,
) -> list[list[list[int]]]:
    return [simplify_segment(segment, tolerance) for segment in segments]


def draw_point_count(
    segments: Sequence[Sequence[Sequence[int]]],
    *,
    steps_per_segment: int,
) -> int:
    count = 0
    for segment in segments:
        if len(segment) < 2:
            continue
        pairs = len(segment) - 1
        count += steps_per_segment + max(0, pairs - 1) * max(1, steps_per_segment - 1)
    return count


def fit_segments_to_point_budget(
    segments: Sequence[Sequence[Sequence[int]]],
    *,
    max_points: int | None,
    steps_per_segment: int,
    initial_tolerance: float,
) -> list[list[list[int]]]:
    fitted = simplify_segments(segments, initial_tolerance)
    if max_points is None or draw_point_count(fitted, steps_per_segment=steps_per_segment) <= max_points:
        return fitted

    tolerance = max(0.25, initial_tolerance)
    for _ in range(20):
        tolerance *= 1.35
        fitted = simplify_segments(segments, tolerance)
        if draw_point_count(fitted, steps_per_segment=steps_per_segment) <= max_points:
            return fitted
    return fitted


def drawing_to_points(
    segments: Sequence[Sequence[Sequence[int]]],
    *,
    steps_per_segment: int = 3,
) -> list[list[int]]:
    points: list[list[int]] = []
    for segment in segments:
        if len(segment) < 2:
            continue
        color = int(segment[0][2])
        for pair_index in range(len(segment) - 1):
            x1, y1, _ = segment[pair_index]
            x2, y2, _ = segment[pair_index + 1]
            for step_index in range(steps_per_segment):
                if pair_index > 0 and step_index == 0:
                    continue
                ratio = step_index / max(1, steps_per_segment - 1)
                x_value = round(x1 + (x2 - x1) * ratio)
                y_value = round(y1 + (y2 - y1) * ratio)
                # Stroke start = color 0 (travel-to-start); rest lit. The
                # stop-marker pass in draw_points_command tags low-nibble 2/3 so the
                # firmware doesn't blank stroke ends early on this textStopTime unit.
                is_stroke_start = pair_index == 0 and step_index == 0
                points.append(
                    [x_value, y_value, 0 if is_stroke_start else color, 0]
                )
    return points


def svg_draw_command(
    path: str,
    *,
    size: int = 640,
    x: int = 0,
    y: int = 0,
    circle_samples: int = 80,
    curve_samples: int = 10,
    arc_samples: int = 80,
    steps_per_segment: int = 2,
    max_points: int | None = 700,
    simplify_tolerance: float = 1.0,
    drop_largest: int = 0,
    largest_last: bool = False,
    white_color: int | None = None,
    red_color: int | None = None,
    override_color: int | None = None,
    cmd_new_type: bool = False,
    cnf_values: list[int] | None = None,
    scale: float = 1.0,
) -> str:
    drawing = read_svg(
        path,
        circle_samples=circle_samples,
        curve_samples=curve_samples,
        arc_samples=arc_samples,
    )
    transformed = transform_segments(drawing, size=size, x=x, y=y)
    color_map = {}
    if white_color is not None:
        color_map[7] = int(white_color)
    if red_color is not None:
        color_map[1] = int(red_color)
    if override_color is not None:
        color_map.update({color_id: int(override_color) for color_id in range(1, 8)})
    transformed = prepare_laser_segments(
        transformed,
        drop_largest=drop_largest,
        largest_last=largest_last,
        color_map=color_map,
    )
    fitted = fit_segments_to_point_budget(
        transformed,
        max_points=max_points,
        steps_per_segment=steps_per_segment,
        initial_tolerance=simplify_tolerance,
    )
    points = drawing_to_points(fitted, steps_per_segment=steps_per_segment)
    return draw_points_command(
        points, cnf_values=cnf_values, cmd_new_type=cmd_new_type, scale=scale
    )


__all__ = [
    "SvgDrawing",
    "SvgSegment",
    "drawing_to_points",
    "draw_point_count",
    "fit_segments_to_point_budget",
    "prepare_laser_segments",
    "read_svg",
    "segment_bbox_area",
    "simplify_segment",
    "simplify_segments",
    "svg_draw_command",
    "transform_segments",
]
