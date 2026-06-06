"""LightElf BLE protocol helpers derived from captured Bluetooth traffic.

This module intentionally contains only packet building/parsing. It does not
talk to Bluetooth hardware, so it is safe to unit-test without a laser nearby.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


UUID_PROFILES = {
    "ff00": {
        "service": "0000FF00-0000-1000-8000-00805F9B34FB",
        "write": "0000FF02-0000-1000-8000-00805F9B34FB",
        "notify": "0000FF01-0000-1000-8000-00805F9B34FB",
    },
    "ffe0": {
        "service": "0000FFE0-0000-1000-8000-00805F9B34FB",
        "write": "0000FFE1-0000-1000-8000-00805F9B34FB",
        "notify": "0000FFE1-0000-1000-8000-00805F9B34FB",
    },
}

REPLY_START_MARKERS = ("E0E1E2E3", "E8E9EAEB", "60616263", "A55A")
REPLY_END_MARKERS = ("E4E5E6E7", "ECEDEEEF")


@dataclass(frozen=True)
class QueryReply:
    raw_hex: str
    challenge_token: str
    challenge_ok: bool
    device_on: bool
    device_type: int
    version: int
    device_number: int
    user_number: int
    ota_version: int


@dataclass(frozen=True)
class PowerState:
    raw_payload: str
    raw_state: int
    on: bool


@dataclass(frozen=True)
class ProjectState:
    """Decoded 9-byte project/pattern selection chunk from the C0 block."""

    project_id: int
    mode_byte: int
    py_mode: int
    preview_pattern: int | None
    selected_words: tuple[int, int, int, int]
    selected_patterns: tuple[int, ...]


@dataclass(frozen=True)
class ModeState:
    raw_payload: str
    mode: int
    color: int
    size_percent: int
    y_size_percent: int
    speed_percent: int
    distance_percent: int
    playback: int
    sound_percent: int
    group_colors: tuple[int, ...]
    text_point_time: int
    draw_point_time: int
    projects: Mapping[int, ProjectState]
    run_direction: int
    xy_tail: tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class SettingsState:
    raw_payload: str
    dmx_address: int
    channel: int
    display_size: int
    xy: int
    red: int
    green: int
    blue: int
    light: int
    cfg: int
    power: int
    brightness: int
    grating: int
    password_status: int
    password: int


@dataclass(frozen=True)
class XYConfigState:
    raw_payload: str
    save: bool
    encoded_auto_value: int
    phase: int
    x_big: int
    x_small: int
    y_big: int
    y_small: int


@dataclass(frozen=True)
class PisEntry:
    index: int | None
    values: tuple[int, ...]
    play_time: float


@dataclass(frozen=True)
class PisState:
    raw_payload: str
    list_mode: bool
    count: int
    entries: tuple[PisEntry, ...]


@dataclass(frozen=True)
class DrawState:
    raw_payload: str
    config_values: tuple[int, ...]
    save_tag: int
    point_count: int | None


@dataclass(frozen=True)
class DeviceState:
    raw_hex: str
    query: QueryReply | None
    power: PowerState | None
    mode: ModeState | None
    settings: SettingsState | None
    xy_config: XYConfigState | None
    pis: PisState | None
    draw: DrawState | None


MODE_IDS = {
    "dmx": 0,
    "random": 1,
    "line": 2,
    "animation": 3,
    "text": 4,
    "christmas": 5,
    "outdoor": 6,
    "program": 7,
    "draw": 8,
    "playlist": 9,
    "aurora": 11,
    "love": 12,
}

PROJECT_MODE_IDS = (2, 3, 5, 6, 11, 12)
OLD_PROJECT_MODE_IDS = (2, 3, 5, 6)
NEW_PROJECT_MODE_IDS = (11, 12)

COLOR_IDS = {
    "default": 0,
    "red": 1,
    "green": 2,
    "blue": 3,
    "yellow": 4,
    "cyan": 5,
    "purple": 6,
    "white": 7,
    "jump": 8,
    "full": 9,
}

PLAYBACK_AUTO = 0
PLAYBACK_SOUND = 255
PROJECT_RANDOM = 0
PROJECT_SELECTED = 255


@dataclass(frozen=True)
class ProjectSelection:
    """Pattern-selection state for one built-in project family.

    Pattern numbers are one-based. They are encoded into
    four little-endian 16-bit bitmasks for up to 64 patterns.
    """

    py_mode: int = PROJECT_RANDOM
    selected_patterns: tuple[int, ...] = ()
    preview_pattern: int | None = None


@dataclass(frozen=True)
class ModeOptions:
    """High-level options for the C0/C4 playback command."""

    mode: int | str
    color: int | str = "full"
    size_percent: int = 50
    speed_percent: int = 50
    distance_percent: int = 50
    playback: int | str = "auto"
    sound_percent: int = 20
    run_direction: int = 0
    text_point_time: int = 50
    group_colors: tuple[int | str, ...] = ()
    projects: Mapping[int | str, ProjectSelection] | None = None
    arb_play: bool = False
    new_prjs: bool = False
    cmd_new_type: bool = False
    text_stop_time: bool = False


@dataclass(frozen=True)
class PisConfig:
    """PIS/project transform parameters, matching captured cnfValus indexes.

    The first fields correspond closely to the manual's DMX channel list:
    color, color flow, graphic group, shape, built-in dynamic effect, effect
    speed, size, zoom, rotations/flips, movement, waves, and gradual drawing.
    """

    color: int = 0
    color_flow: int = 0
    graphic_group: int = 0
    shape: int = 0
    dynamic_effect: int = 0
    effect_speed: int = 0
    size: int = 50
    zoom: int = 0
    rotate_z: int = 0
    rotate_x: int = 0
    rotate_y: int = 0
    move_x: int = 0
    move_y: int = 0
    play_time: float = 3.0
    wave_x: int = 0
    gradient: int = 0
    extra_16: int = 0
    extra_17: int = 0
    extra_18: int = 0


def clean_hex(value: str) -> str:
    compact = "".join(value.split()).upper()
    if len(compact) % 2:
        raise ValueError("hex string length must be even")
    int(compact or "00", 16)
    return compact


def block_payload(
    value: str,
    start_marker: str,
    end_marker: str,
    *,
    missing_ok: bool = False,
) -> str | None:
    """Extract a marker-delimited payload, or treat marker-free input as payload.

    Captured controller traffic uses non-greedy marker matching for most blocks.
    This helper follows that behavior for one block and is deliberately
    tolerant of already-sliced payloads so generated commands can be parsed in
    unit tests.
    """

    data = clean_hex(value)
    start = clean_hex(start_marker)
    end = clean_hex(end_marker)
    start_index = data.find(start)
    if start_index >= 0:
        payload_start = start_index + len(start)
        end_index = data.find(end, payload_start)
        if end_index < 0:
            if missing_ok:
                return None
            raise ValueError(f"missing end marker {end_marker}")
        return data[payload_start:end_index]

    if end in data:
        if missing_ok:
            return None
        raise ValueError(f"missing start marker {start_marker}")

    if missing_ok:
        return None
    return data


def _byte(payload: str, one_based_index: int, default: int | None = None) -> int:
    start = 2 * (one_based_index - 1)
    end = start + 2
    if start < 0 or end > len(payload):
        if default is None:
            raise ValueError(f"payload missing byte {one_based_index}")
        return default
    return int(payload[start:end], 16)


def _word(payload: str, one_based_index: int, default: int | None = None) -> int:
    start = 2 * (one_based_index - 1)
    end = start + 4
    if start < 0 or end > len(payload):
        if default is None:
            raise ValueError(f"payload missing word at byte {one_based_index}")
        return default
    return int(payload[start:end], 16)


def _bytes(payload: str, one_based_index: int, count: int) -> tuple[int, ...]:
    return tuple(_byte(payload, one_based_index + index, 0) for index in range(count))


def _percent_from_byte(value: int) -> int:
    return round((value / 255) * 100)


def patterns_from_words(words: Sequence[int]) -> tuple[int, ...]:
    patterns: list[int] = []
    for word_index, word in enumerate(words):
        for bit_index in range(16):
            if int(word) & (1 << bit_index):
                patterns.append(word_index * 16 + bit_index + 1)
    return tuple(patterns)


def byte_hex(value: int, width: int = 2) -> str:
    value = int(round(value))
    if value < 0:
        value = 0x8000 | (-value)
    return f"{value:04x}"[-width:].upper()


def percent_hex(value: int | float) -> str:
    return byte_hex(clamp(value, 0, 100) * 255 / 100, 2)


def clamp(value: int | float, low: int, high: int) -> int:
    return max(low, min(high, int(round(value))))


def resolve_id(value: int | str, mapping: Mapping[str, int], label: str) -> int:
    if isinstance(value, str):
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        if key not in mapping:
            known = ", ".join(sorted(mapping))
            raise ValueError(f"unknown {label} {value!r}; known: {known}")
        return mapping[key]
    return int(value)


def playback_id(value: int | str) -> int:
    if isinstance(value, str):
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        if key in {"auto", "automatic"}:
            return PLAYBACK_AUTO
        if key in {"sound", "music", "voice", "audio"}:
            return PLAYBACK_SOUND
        raise ValueError("playback must be auto or sound/music")
    return int(value)


def pattern_words(patterns: Sequence[int]) -> list[int]:
    words = [0, 0, 0, 0]
    for pattern in patterns:
        index = int(pattern) - 1
        if index < 0 or index >= 64:
            raise ValueError("pattern numbers are one-based and must be 1..64")
        words[index // 16] |= 1 << (index % 16)
    return words


def hex_to_bytes(value: str) -> bytes:
    return bytes.fromhex(clean_hex(value))


def chunk_hex(value: str, chunk_size: int = 20) -> list[bytes]:
    data = hex_to_bytes(value)
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def checksum16(value: str) -> str:
    data = hex_to_bytes(value)
    return f"{sum(data) & 0xffff:04X}"


def query_command(random_bytes: Sequence[int]) -> str:
    if len(random_bytes) != 4:
        raise ValueError("query requires exactly four random bytes")
    return "E0E1E2E3" + "".join(byte_hex(x, 2) for x in random_bytes) + "E4E5E6E7"


def expected_challenge_token(random_bytes: Sequence[int]) -> str:
    if len(random_bytes) != 4:
        raise ValueError("challenge requires exactly four random bytes")
    b0 = (((random_bytes[0] + 55) >> 1) - 10) & 0xFF
    b1 = (7 + ((random_bytes[1] - 68) << 1)) & 0xFF
    b2 = (15 + ((random_bytes[2] + 97) >> 1)) & 0xFF
    b3 = (87 + ((random_bytes[3] - 127) >> 1)) & 0xFF
    return "".join(byte_hex(x, 2) for x in (b0, b1, b2, b3))


def parse_query_reply(response_hex: str, random_bytes: Sequence[int]) -> QueryReply:
    response = clean_hex(response_hex)
    if len(response) < 24:
        raise ValueError("query reply is too short")

    token = response[-24:-16]
    expected = expected_challenge_token(random_bytes)
    ok = token == expected or token == "8AC5624F"

    def at(start: int, end: int) -> int:
        return int(response[start:end], 16)

    return QueryReply(
        raw_hex=response,
        challenge_token=token,
        challenge_ok=ok,
        device_on=at(-16, -14) != 0,
        device_type=at(-14, -12),
        version=at(-12, -10),
        device_number=at(8, 10),
        user_number=at(-10, -8),
        ota_version=at(10, 14),
    )


def parse_power_block(value: str) -> PowerState:
    payload = block_payload(value, "B0B1B2B3", "B4B5B6B7")
    if payload is None or len(payload) < 2:
        raise ValueError("missing power payload")
    state = _byte(payload, 1)
    return PowerState(raw_payload=payload, raw_state=state, on=state != 0)


def _parse_project_state(payload: str, project_id: int, one_based_index: int) -> ProjectState:
    mode_byte = _byte(payload, one_based_index, 0)
    words_high_to_low = (
        _word(payload, one_based_index + 1, 0),
        _word(payload, one_based_index + 3, 0),
        _word(payload, one_based_index + 5, 0),
        _word(payload, one_based_index + 7, 0),
    )
    words = tuple(reversed(words_high_to_low))
    preview = mode_byte & 0x7F
    return ProjectState(
        project_id=project_id,
        mode_byte=mode_byte,
        py_mode=PROJECT_SELECTED if mode_byte & 0x80 else PROJECT_RANDOM,
        preview_pattern=preview or None,
        selected_words=words,  # type: ignore[arg-type]
        selected_patterns=patterns_from_words(words),
    )


def parse_mode_block(value: str) -> ModeState:
    payload = block_payload(value, "C0C1C2C3", "C4C5C6C7")
    if payload is None:
        raise ValueError("missing mode payload")
    if len(payload) < 192:
        raise ValueError(f"mode payload should be 96 bytes; got {len(payload) // 2}")
    payload = payload[:192]

    projects: dict[int, ProjectState] = {}
    offset = 17
    for project_id in OLD_PROJECT_MODE_IDS:
        projects[project_id] = _parse_project_state(payload, project_id, offset)
        offset += 9

    run_direction = _byte(payload, offset, 0)
    offset += 1
    xy_tail = _bytes(payload, offset, 6)
    offset += 6

    for project_id in NEW_PROJECT_MODE_IDS:
        projects[project_id] = _parse_project_state(payload, project_id, offset)
        offset += 9

    group_bytes = _bytes(payload, 11, 4)
    return ModeState(
        raw_payload=payload,
        mode=_byte(payload, 1, 0),
        color=_byte(payload, 3, 0),
        size_percent=_percent_from_byte(_byte(payload, 4, 0)),
        y_size_percent=_percent_from_byte(_byte(payload, 5, 0)),
        speed_percent=_percent_from_byte(_byte(payload, 6, 0)),
        distance_percent=_percent_from_byte(_byte(payload, 8, 0)),
        playback=_byte(payload, 9, 0),
        sound_percent=_percent_from_byte(_byte(payload, 10, 0)),
        group_colors=tuple(color for color in group_bytes if color != 0xFF),
        text_point_time=_byte(payload, 15, 0),
        draw_point_time=_byte(payload, 16, 0),
        projects=projects,
        run_direction=run_direction,
        xy_tail=xy_tail,  # type: ignore[arg-type]
    )


def parse_settings_block(value: str) -> SettingsState:
    payload = block_payload(value, "00010203", "04050607")
    if payload is None:
        raise ValueError("missing settings payload")
    if len(payload) < 22:
        raise ValueError(f"settings payload should be at least 11 bytes; got {len(payload) // 2}")
    return SettingsState(
        raw_payload=payload,
        dmx_address=_word(payload, 1, 1),
        channel=_byte(payload, 3, 0),
        display_size=_byte(payload, 4, 10),
        xy=_byte(payload, 5, 0),
        red=_byte(payload, 6, 255),
        green=_byte(payload, 7, 255),
        blue=_byte(payload, 8, 255),
        light=_byte(payload, 9, 3),
        cfg=_byte(payload, 10, 0),
        power=_byte(payload, 11, 0),
        brightness=_byte(payload, 12, 0),
        grating=_byte(payload, 13, 0),
        password_status=_byte(payload, 14, 0),
        password=_word(payload, 15, 0),
    )


def parse_xy_config_block(value: str) -> XYConfigState:
    payload = block_payload(value, "10111213", "14151617")
    if payload is None:
        raise ValueError("missing XY config payload")
    if len(payload) < 14:
        raise ValueError(f"XY config payload should be at least 7 bytes; got {len(payload) // 2}")
    return XYConfigState(
        raw_payload=payload,
        save=_byte(payload, 1, 0) != 0xFF,
        encoded_auto_value=_byte(payload, 2, 0),
        phase=_byte(payload, 3, 0),
        x_big=_byte(payload, 4, 0),
        x_small=_byte(payload, 5, 0),
        y_big=_byte(payload, 6, 0),
        y_small=_byte(payload, 7, 0),
    )


def _parse_pis_entry(
    payload: str,
    *,
    index: int | None,
    cmd_new_type: bool,
    xy_cnf: bool,
) -> PisEntry:
    base_values = [_byte(payload, pos, 0) for pos in range(1, min(13, len(payload) // 2) + 1)]
    play_raw = _word(payload, 14, 0) if cmd_new_type else _byte(payload, 14, 0)
    values = base_values + [play_raw]
    extra_start = 16 if cmd_new_type else 15
    while (extra_start - 1) * 2 < len(payload):
        values.append(_byte(payload, extra_start, 0))
        extra_start += 1
    if not xy_cnf:
        values = values[:14]
    return PisEntry(index=index, values=tuple(values), play_time=play_raw / 10)


def parse_pis_block(
    value: str,
    *,
    cmd_new_type: bool = False,
    xy_cnf: bool = False,
) -> PisState:
    payload = block_payload(value, "D0D1D2D3", "D4D5D6D7")
    if payload is None or len(payload) < 4:
        raise ValueError("missing PIS payload")

    first = _byte(payload, 1, 0)
    count = first & 0x7F
    list_mode = bool(first & 0x80)
    entry_payload_bytes = 21 if xy_cnf else 15
    stride_bytes = entry_payload_bytes + 1
    entries: list[PisEntry] = []

    for entry_index in range(count):
        start_byte = 3 + entry_index * stride_bytes
        start = (start_byte - 1) * 2
        end = start + entry_payload_bytes * 2
        if end > len(payload):
            break
        raw_entry = payload[start:end]
        entries.append(
            _parse_pis_entry(
                raw_entry,
                index=None if list_mode else _byte(payload, 2, 0),
                cmd_new_type=cmd_new_type,
                xy_cnf=xy_cnf,
            )
        )

    return PisState(
        raw_payload=payload,
        list_mode=list_mode,
        count=count,
        entries=tuple(entries),
    )


def parse_draw_block(value: str) -> DrawState:
    payload = block_payload(value, "F0F1F2F3", "F4F5F6F7")
    if payload is None:
        raise ValueError("missing draw payload")
    if len(payload) < 32:
        raise ValueError(f"draw payload should be at least 16 bytes; got {len(payload) // 2}")
    config_values = _bytes(payload, 1, 15)
    save_tag = _byte(payload, 16, 0)
    point_count = _word(payload, 17, 0) if save_tag == 0 and len(payload) >= 36 else None
    return DrawState(
        raw_payload=payload,
        config_values=config_values,
        save_tag=save_tag,
        point_count=point_count,
    )


def parse_device_state(
    value: str,
    *,
    query: QueryReply | None = None,
    cmd_new_type: bool = False,
    xy_cnf: bool = False,
) -> DeviceState:
    raw = clean_hex(value)

    def optional(parser, *args, **kwargs):
        try:
            return parser(*args, **kwargs)
        except ValueError:
            return None

    def optional_block(start_marker: str, end_marker: str, parser, *args, **kwargs):
        if clean_hex(start_marker) not in raw or clean_hex(end_marker) not in raw:
            return None
        return optional(parser, *args, **kwargs)

    return DeviceState(
        raw_hex=raw,
        query=query,
        power=optional_block("B0B1B2B3", "B4B5B6B7", parse_power_block, raw),
        mode=optional_block("C0C1C2C3", "C4C5C6C7", parse_mode_block, raw),
        settings=optional_block("00010203", "04050607", parse_settings_block, raw),
        xy_config=optional_block("10111213", "14151617", parse_xy_config_block, raw),
        pis=optional_block(
            "D0D1D2D3",
            "D4D5D6D7",
            parse_pis_block,
            raw,
            cmd_new_type=cmd_new_type,
            xy_cnf=xy_cnf,
        ),
        draw=optional_block("F0F1F2F3", "F4F5F6F7", parse_draw_block, raw),
    )


def reply_complete(buffer_hex: str) -> bool:
    buffer = clean_hex(buffer_hex)
    return any(buffer.endswith(marker) for marker in REPLY_END_MARKERS)


def power_command(on: bool, *, cmd_new_type: bool = True) -> str:
    state = "FF" if on else "00"
    if cmd_new_type:
        return f"B0B1B2B3{state}00000000000000B4B5B6B7"
    return f"B0B1B2B3{state}B4B5B6B7"


def packed_nibbles(high: int, low: int) -> str:
    return byte_hex(((int(high) & 0x0F) << 4) | (int(low) & 0x0F), 2)


def draw_points_command(
    points: Sequence[Sequence[int | float]],
    *,
    cnf_values: Sequence[int] | None = None,
    cmd_new_type: bool = False,
    pics_play: bool = False,
    text_stop_time: bool = False,
    tx_point_time: int = 50,
    play_time: float | None = None,
    save_tag: int = 0,
    stop_markers: bool = True,
) -> str:
    """Build an F0/F4 hand-draw command for projector-space points.

    Point records are ``x, y, color/control, blanking/control``. Coordinates are
    in the projector's -400..400 coordinate space.

    ``stop_markers`` applies the low-nibble pass that this old-protocol unit
    (device_type=0) requires: a color-0 point becomes low-nibble
    2 (travel-to-start), and any lit point that is the last of a stroke — i.e. the
    final point overall or the point right before a color-0 travel point becomes
    low-nibble 3 (stop). Without the 3 marker the firmware blanks the last segment
    of each stroke early, leaving a gap at the start/stop point. See
    ``analysis/animation_and_draw_semantics.md``.
    """

    config = list(cnf_values or [])
    payload = ""
    for index in range(15):
        if index <= 12:
            payload += byte_hex(config[index] if index < len(config) else 0, 2)
        elif index == 13 and pics_play:
            payload += byte_hex(10 * (tx_point_time if play_time is None else play_time), 2)
        elif index == 14 and text_stop_time:
            payload += byte_hex(tx_point_time, 2)
        else:
            payload += "00"

    payload += byte_hex(save_tag, 2)
    if save_tag == 0:
        safe_points = list(points) or [[0, 0, 0, 1], [0, 0, 0, 1]]
        payload += byte_hex(len(safe_points), 4)
        last_index = len(safe_points) - 1
        for index, point in enumerate(safe_points):
            if len(point) != 4:
                raise ValueError("draw points must be x, y, color/control, blanking/control")
            x_value, y_value, color, blanking = point
            low = int(blanking)
            if stop_markers and not cmd_new_type:
                # Apply the stop-marker low-nibble pass.
                if int(color) == 0:
                    low = 2  # travel-to-start / blanked point
                elif index == last_index or int(safe_points[index + 1][2]) == 0:
                    low = 3  # last lit point of this stroke -> stop marker
                else:
                    low = int(blanking)  # lit interior: keep source blanking
                    # (our own builders pass 0 here; built-in frames may carry
                    # corner=1 / dwell markers that are preserved verbatim)
            if cmd_new_type:
                payload += (
                    byte_hex(x_value, 4)
                    + byte_hex(y_value, 4)
                    + byte_hex(color, 2)
                    + packed_nibbles(0, int(blanking))
                )
            else:
                payload += (
                    byte_hex(x_value, 4)
                    + byte_hex(y_value, 4)
                    + packed_nibbles(int(color), low)
                )

    if cmd_new_type:
        checksum = checksum16(payload)
        return ("F0F1F200" + payload + checksum + "F6F7").upper()
    if pics_play:
        return ("F01FF200" + payload + "F4F5F6F7").upper()
    return ("F0F1F2F3" + payload + "F4F5F6F7").upper()


def draw_line_command(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    color: int = 7,
    steps: int = 16,
    cmd_new_type: bool = False,
) -> str:
    if steps < 2:
        raise ValueError("draw line requires at least two points")
    # First point = start with color 0 (travel-to-start); the rest are lit. The
    # firmware's stop-marker pass in draw_points_command turns the leading color-0
    # point into low-nibble 2 and the final lit point into 3, which this
    # textStopTime unit needs to avoid blanking the last segment early.
    points = []
    for index in range(steps):
        ratio = index / (steps - 1)
        x_value = round(x1 + (x2 - x1) * ratio)
        y_value = round(y1 + (y2 - y1) * ratio)
        points.append([x_value, y_value, 0 if index == 0 else color, 0])
    return draw_points_command(points, cmd_new_type=cmd_new_type)


def draw_polyline_command(
    vertices: Sequence[Sequence[int | float]],
    *,
    color: int = 7,
    steps_per_segment: int = 8,
    closed: bool = False,
    corner_dwell: int = 2,
    cmd_new_type: bool = False,
) -> str:
    if len(vertices) < 2:
        raise ValueError("draw polyline requires at least two vertices")
    if steps_per_segment < 2:
        raise ValueError("draw polyline requires at least two steps per segment")

    path = [list(vertex) for vertex in vertices]
    if closed:
        path.append(path[0])

    # One continuous stroke: first point color 0 (travel-to-start), rest lit. For a
    # closed shape the caller repeats the start vertex as the final point so the
    # loop closes; the stop-marker pass tags the final lit point with low-nibble 3.
    # corner_dwell repeats each vertex N extra times so the galvo settles and the
    # corner stays sharp instead of arcing (the galvo can't change direction
    # instantly). 0 = off (fastest, roundest corners); 2-3 = crisp corners.
    points = []
    for segment_index in range(len(path) - 1):
        x1, y1 = path[segment_index]
        x2, y2 = path[segment_index + 1]
        for step_index in range(steps_per_segment):
            if segment_index > 0 and step_index == 0:
                continue
            ratio = step_index / (steps_per_segment - 1)
            x_value = round(x1 + (x2 - x1) * ratio)
            y_value = round(y1 + (y2 - y1) * ratio)
            points.append([x_value, y_value, 0 if not points else color, 0])
            # Dwell at each interior vertex (segment end) to sharpen the corner.
            if corner_dwell and step_index == steps_per_segment - 1:
                points.extend([[x_value, y_value, color, 0]] * corner_dwell)
    return draw_points_command(points, cmd_new_type=cmd_new_type)


def segments_to_points(
    segments: Sequence[Sequence[Sequence[int | float]]],
    *,
    color: int = 7,
    steps_per_segment: int = 6,
) -> list[list[int]]:
    """Interpolate a list of strokes into F0/F4 [x, y, color, blanking] records.

    Each stroke's first point is color 0 (travel-to-start); the rest are lit. The
    stop-marker pass in draw_points_command tags low-nibble 2/3. Exposed separately
    so the motion engine can animate the same point set.
    """
    points: list[list[int]] = []
    for segment in segments:
        if len(segment) < 2:
            continue
        for pair_index in range(len(segment) - 1):
            x1, y1 = segment[pair_index]
            x2, y2 = segment[pair_index + 1]
            for step_index in range(steps_per_segment):
                if pair_index > 0 and step_index == 0:
                    continue
                ratio = step_index / (steps_per_segment - 1)
                x_value = round(x1 + (x2 - x1) * ratio)
                y_value = round(y1 + (y2 - y1) * ratio)
                is_segment_start = pair_index == 0 and step_index == 0
                points.append([x_value, y_value, 0 if is_segment_start else color, 0])
    return points


def draw_segments_command(
    segments: Sequence[Sequence[Sequence[int | float]]],
    *,
    color: int = 7,
    steps_per_segment: int = 6,
    cmd_new_type: bool = False,
) -> str:
    points = segments_to_points(segments, color=color, steps_per_segment=steps_per_segment)
    return draw_points_command(points, cmd_new_type=cmd_new_type)


def draw_box_command(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    color: int = 7,
    steps_per_edge: int = 6,
    corner_dwell: int = 2,
    cmd_new_type: bool = False,
) -> str:
    return draw_polyline_command(
        [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]],
        color=color,
        steps_per_segment=steps_per_edge,
        closed=False,
        corner_dwell=corner_dwell,
        cmd_new_type=cmd_new_type,
    )


TEXT_STROKES = {
    "0": ("a", "b", "c", "d", "e", "f"),
    "1": ("b", "c"),
    "2": ("a", "b", "g", "e", "d"),
    "3": ("a", "b", "g", "c", "d"),
    "4": ("f", "g", "b", "c"),
    "5": ("a", "f", "g", "c", "d"),
    "6": ("a", "f", "g", "c", "d", "e"),
    "7": ("a", "b", "c"),
    "8": ("a", "b", "c", "d", "e", "f", "g"),
    "9": ("a", "b", "c", "d", "f", "g"),
    "A": ("a", "b", "c", "e", "f", "g"),
    "B": ("a", "b", "c", "d", "e", "f", "g"),
    "C": ("a", "d", "e", "f"),
    "D": ("a", "b", "c", "d", "e", "f"),
    "E": ("a", "d", "e", "f", "g"),
    "F": ("a", "e", "f", "g"),
    "G": ("a", "c", "d", "e", "f", "g"),
    "H": ("b", "c", "e", "f", "g"),
    "I": ("a", "d", "vu", "vd"),
    "J": ("b", "c", "d", "e"),
    "K": ("e", "f", "ur", "lr"),
    "L": ("d", "e", "f"),
    "M": ("b", "c", "e", "f", "ul", "ur"),
    "N": ("b", "c", "e", "f", "diag_down"),
    "O": ("a", "b", "c", "d", "e", "f"),
    "P": ("a", "b", "e", "f", "g"),
    "Q": ("a", "b", "c", "d", "e", "f", "lr"),
    "R": ("a", "b", "e", "f", "g", "lr"),
    "S": ("a", "c", "d", "f", "g"),
    "T": ("a", "vu", "vd"),
    "U": ("b", "c", "d", "e", "f"),
    "V": ("vleft", "vright"),
    "W": ("b", "c", "e", "f", "ll", "lr"),
    "X": ("diag_down", "diag_up"),
    "Y": ("ul", "ur", "vd"),
    "Z": ("a", "d", "diag_up"),
    "-": ("g",),
    "_": ("d",),
}

TEXT_SEGMENTS = {
    "a": ((0, 6), (4, 6)),
    "b": ((4, 6), (4, 3)),
    "c": ((4, 3), (4, 0)),
    "d": ((0, 0), (4, 0)),
    "e": ((0, 3), (0, 0)),
    "f": ((0, 6), (0, 3)),
    "g": ((0, 3), (4, 3)),
    "vu": ((2, 6), (2, 3)),
    "vd": ((2, 3), (2, 0)),
    "ul": ((0, 6), (2, 3)),
    "ur": ((4, 6), (2, 3)),
    "ll": ((0, 0), (2, 3)),
    "lr": ((2, 3), (4, 0)),
    "diag_down": ((0, 6), (4, 0)),
    "diag_up": ((0, 0), (4, 6)),
    "vleft": ((0, 6), (2, 0)),
    "vright": ((4, 6), (2, 0)),
}


def draw_text_command(
    text: str,
    *,
    x: int = 0,
    y: int = 0,
    size: int = 180,
    color: int = 7,
    steps_per_stroke: int = 5,
    cmd_new_type: bool = False,
) -> str:
    text = text.upper()
    char_width = 4.0
    char_gap = 1.5
    scale = size / 6.0
    visible_count = max(1, len(text))
    total_width = (visible_count * char_width + max(0, visible_count - 1) * char_gap) * scale
    left = x - total_width / 2
    bottom = y - size / 2

    segments = []
    for char_index, char in enumerate(text):
        if char == " ":
            continue
        x_offset = left + char_index * (char_width + char_gap) * scale
        for segment_name in TEXT_STROKES.get(char, ()):
            segment = TEXT_SEGMENTS[segment_name]
            mapped = []
            for sx, sy in segment:
                mapped.append([x_offset + sx * scale, bottom + sy * scale])
            segments.append(mapped)

    return draw_segments_command(
        segments,
        color=color,
        steps_per_segment=steps_per_stroke,
        cmd_new_type=cmd_new_type,
    )


def settings_command(
    *,
    dmx_address: int = 1,
    channel: int = 0,
    display_size: int = 10,
    xy: int = 0,
    red: int = 255,
    green: int = 255,
    blue: int = 255,
    light: int = 3,
    cfg: int = 0,
    power: int = 0,
    brightness: int = 50,
    grating: int = 5,
    password_status: int = 255,
    password: int = 6688,
    cmd_new_type: bool = True,
) -> str:
    if cfg == 0:
        red = green = blue = 255
    payload = (
        byte_hex(dmx_address, 4)
        + byte_hex(channel, 2)
        + byte_hex(display_size, 2)
        + byte_hex(xy, 2)
        + byte_hex(red, 2)
        + byte_hex(green, 2)
        + byte_hex(blue, 2)
        + byte_hex(light, 2)
        + byte_hex(cfg, 2)
        + byte_hex(power, 2)
    )
    if cmd_new_type:
        payload += (
            byte_hex(brightness, 2)
            + byte_hex(grating, 2)
            + byte_hex(password_status, 2)
            + byte_hex(password, 4)
        )
    else:
        payload += "0000000000"
    return "00010203" + payload + "04050607"


def binary64_to_8_bytes(bits: str = "") -> str:
    padded = ("0" * 64 + str(bits))[-64:]
    if any(char not in "01" for char in padded):
        raise ValueError("binary selector strings may contain only 0 and 1")
    return "".join(byte_hex(int(padded[index : index + 8], 2), 2) for index in range(0, 64, 8))


def image_list_command(counts: Sequence[int] = (0,), selected_bits: str = "") -> str:
    payload = byte_hex(len(counts), 2) + binary64_to_8_bytes(selected_bits)
    payload += "FF" * 7
    for count in counts:
        payload += byte_hex(count, 4)
    used_bytes = len(payload) // 2
    payload += "00" * max(0, 144 - used_bytes)
    return ("90919293" + payload[: 144 * 2] + "94959697").upper()


def point_play_command(selected_bits: str = "") -> str:
    return ("70717073" + binary64_to_8_bytes(selected_bits) + "00" * 24 + "74757677").upper()


def pis_values(config: PisConfig | Sequence[int]) -> list[int]:
    if isinstance(config, PisConfig):
        return [
            config.color,
            config.color_flow,
            config.graphic_group,
            config.shape,
            config.dynamic_effect,
            config.effect_speed,
            config.size,
            config.zoom,
            config.rotate_z,
            config.rotate_x,
            config.rotate_y,
            config.move_x,
            config.move_y,
            round(10 * config.play_time),
            config.wave_x,
            config.gradient,
            config.extra_16,
            config.extra_17,
            config.extra_18,
        ]
    values = list(config)
    return values + [0] * max(0, 19 - len(values))


def pis_payload(
    config: PisConfig | Sequence[int],
    *,
    cmd_new_type: bool = False,
    xy_cnf: bool = False,
) -> str:
    values = pis_values(config)
    payload = "".join(byte_hex(values[index], 2) for index in range(13))
    play_time_width = 4 if cmd_new_type else 2
    payload += byte_hex(values[13], play_time_width)
    if xy_cnf:
        payload += "".join(byte_hex(values[index], 2) for index in range(14, 19))
        target_bytes = 21
    else:
        target_bytes = 15
    payload += "00" * max(0, target_bytes - len(payload) // 2)
    return payload


def pis_command(
    index: int,
    config: PisConfig | Sequence[int],
    *,
    cmd_new_type: bool = False,
    xy_cnf: bool = False,
) -> str:
    return (
        "D0D1D2D301"
        + byte_hex(index, 2)
        + pis_payload(config, cmd_new_type=cmd_new_type, xy_cnf=xy_cnf)
        + "00D4D5D6D7"
    ).upper()


def pis_list_command(
    configs: Sequence[PisConfig | Sequence[int]],
    *,
    cmd_new_type: bool = False,
    xy_cnf: bool = False,
) -> str:
    count = len(configs)
    if count > 127:
        raise ValueError("PIS list count must fit in 7 bits")
    payload = byte_hex(0x80 | count, 2) + "00"
    for config in configs:
        payload += pis_payload(config, cmd_new_type=cmd_new_type, xy_cnf=xy_cnf) + "FF"
    return ("D0D1D2D3" + payload + "D4D5D6D7").upper()


def xy_config_command(
    *,
    auto: bool = True,
    auto_value: int = 0,
    phase: int = 0,
    x_big: int = 0,
    x_small: int = 0,
    y_big: int = 0,
    y_small: int = 0,
    save: bool = True,
) -> str:
    payload = "00" if save else "FF"
    payload += byte_hex(auto_value if auto else 255 - auto_value, 2)
    payload += byte_hex(phase, 2)
    payload += byte_hex(x_big, 2)
    payload += byte_hex(x_small, 2)
    payload += byte_hex(y_big, 2)
    payload += byte_hex(y_small, 2)
    payload += "00" * max(0, 16 - len(payload) // 2)
    return ("10111213" + payload[:32] + "14151617").upper()


def coerce_project_selection(value: ProjectSelection | Sequence[int] | None) -> ProjectSelection:
    if value is None:
        return ProjectSelection()
    if isinstance(value, ProjectSelection):
        return value
    if isinstance(value, Mapping):
        raw_patterns = (
            value.get("selected_patterns")
            or value.get("patterns")
            or value.get("selected")
            or ()
        )
        if isinstance(raw_patterns, str):
            selected = tuple(int(item.strip()) for item in raw_patterns.split(",") if item.strip())
        else:
            selected = tuple(int(item) for item in raw_patterns)
        py_mode = int(value.get("py_mode", PROJECT_SELECTED if selected else PROJECT_RANDOM))
        preview = value.get("preview_pattern", value.get("preview"))
        return ProjectSelection(
            py_mode=py_mode,
            selected_patterns=selected,
            preview_pattern=None if preview in (None, "") else int(preview),
        )
    selected = tuple(int(item) for item in value)
    return ProjectSelection(
        py_mode=PROJECT_SELECTED if selected else PROJECT_RANDOM,
        selected_patterns=selected,
    )


def project_payload(
    selection: ProjectSelection | Sequence[int] | None,
    *,
    preview_pattern: int | None = None,
) -> str:
    item = coerce_project_selection(selection)
    pattern = item.preview_pattern if preview_pattern is None else preview_pattern
    mode_byte = 0 if item.py_mode == 0 else 0x80
    if pattern is not None:
        if pattern < 1 or pattern > 127:
            raise ValueError("preview pattern must be one-based and fit in 1..127")
        mode_byte |= pattern
    words = pattern_words(item.selected_patterns)
    payload = byte_hex(mode_byte, 2)
    for word in reversed(words):
        payload += byte_hex(word, 4)
    return payload


def group_color_payload(
    group_colors: Sequence[int | str],
    *,
    text_stop_time: bool,
    text_point_time: int,
) -> str:
    if not group_colors:
        return "FFFFFFFF0000"
    payload = "".join(byte_hex(resolve_id(color, COLOR_IDS, "color"), 2) for color in group_colors)
    payload = (payload + "FFFFFFFF")[:8]
    if text_stop_time:
        payload += byte_hex(text_point_time, 2)
    payload = (payload + "0000")[:12]
    return payload


def mode_command(
    options: ModeOptions | None = None,
    **kwargs: object,
) -> str:
    if options is None:
        options = ModeOptions(**kwargs)  # type: ignore[arg-type]
    elif kwargs:
        raise TypeError("pass either a ModeOptions object or keyword options, not both")

    mode_id = resolve_id(options.mode, MODE_IDS, "mode")
    color_id = resolve_id(options.color, COLOR_IDS, "color")
    playback = playback_id(options.playback)
    projects = options.projects or {}

    payload = (
        byte_hex(mode_id, 2)
        + "00"
        + byte_hex(color_id, 2)
        + percent_hex(options.size_percent)
        + percent_hex(options.size_percent)
        + percent_hex(options.speed_percent)
        + "00"
        + percent_hex(options.distance_percent)
        + byte_hex(playback, 2)
        + percent_hex(options.sound_percent)
        + group_color_payload(
            options.group_colors,
            text_stop_time=options.text_stop_time,
            text_point_time=options.text_point_time,
        )
    )

    for project_id in OLD_PROJECT_MODE_IDS:
        payload += project_payload(projects.get(project_id) or projects.get(str(project_id)))

    include_direction = options.arb_play or options.cmd_new_type
    tail = byte_hex(options.run_direction if include_direction else 0, 2) + "00" * 6

    if options.new_prjs:
        for project_id in NEW_PROJECT_MODE_IDS:
            tail += project_payload(projects.get(project_id) or projects.get(str(project_id)))

    tail += "00" * max(0, 44 - len(tail) // 2)
    payload += tail[: 44 * 2]
    return ("C0C1C2C3" + payload + "C4C5C6C7").upper()


def simple_mode_command(
    *,
    mode: int,
    color: int = 9,
    size_percent: int = 50,
    speed_percent: int = 50,
    distance_percent: int = 50,
    random_mode: int = 0,
    sound_percent: int = 20,
) -> str:
    """Build a conservative C0/C4 mode command with empty project selections."""
    return mode_command(
        mode=mode,
        color=color,
        size_percent=size_percent,
        speed_percent=speed_percent,
        distance_percent=distance_percent,
        playback=random_mode,
        sound_percent=sound_percent,
    )


def send_script_to_chunks(script: str, chunk_size: int = 20) -> list[bytes | str]:
    """Apply captured R/Z send-script behavior, then chunk hex parts."""

    parts: list[str] = []
    current = ""
    for char in clean_script(script):
        if char == "R":
            if current:
                parts.append(current)
                current = ""
            parts.append("reply")
        elif char == "Z":
            if current:
                parts.append(current)
                current = ""
            parts.append("split")
        else:
            current += char
    if current:
        parts.append(current)

    chunks: list[bytes | str] = []
    for part in parts:
        if part in {"reply", "split"}:
            chunks.append(part)
        else:
            chunks.extend(chunk_hex(part, chunk_size))
    return chunks


def clean_script(script: str) -> str:
    return "".join(script.split()).upper()


def stitch_notifications(notifications: Iterable[bytes]) -> str:
    return "".join(chunk.hex().upper() for chunk in notifications)
