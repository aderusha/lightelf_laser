"""Constants for the LightElf Laser integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.const import Platform

DOMAIN = "lightelf_laser"
LOGGER = logging.getLogger(__package__)

DEFAULT_NAME = "LightElf Laser"
DEFAULT_ADDRESS = ""
DEFAULT_TIMEOUT = 10
UPDATE_INTERVAL = timedelta(seconds=30)

CONF_NAME = "name"
CONF_TIMEOUT = "timeout"

TRANSPORT_BLUETOOTH = "bluetooth"

LIGHTELF_SERVICE_UUIDS = (
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "0000ffe0-0000-1000-8000-00805f9b34fb",
)

# Folder under Home Assistant's local media tree where users upload SVG files.
# The SVG select entity lists *.svg from here and the Show SVG button draws the
# choice. HAOS exposes this as /media in the Core container and
# /mnt/data/supervisor/media on the host.
SVG_MEDIA_SUBDIR = "lightelf_laser/svg"
# Previous config-dir location; files are migrated to the media folder on scan.
SVG_LEGACY_SUBDIR = "lightelf_laser/svg"
STARTER_SVG_DIR = "starter_svgs"

PLATFORMS: tuple[Platform, ...] = (
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.TEXT,
    Platform.IMAGE,
    Platform.BUTTON,
)

# Device beam-color indices (high nibble of the F0/F4 point control byte and the
# C0 mode color field). Defined early because several option lists derive from it.
COLOR_OPTIONS = {
    "red": 1,
    "green": 2,
    "blue": 3,
    "yellow": 4,
    "cyan": 5,
    "purple": 6,
    "white": 7,
}

# "rainbow" is not a device color index; it means cycle colors per stroke.
# Offered for text only.
RAINBOW = "rainbow"
TEXT_COLOR_OPTIONS = list(COLOR_OPTIONS) + [RAINBOW]

# Built-in shape library (bundled). Thumbnails live in <component>/builtin/
# as "<Family>_<index:03d>.png"; point frames in builtin_patterns.json.
BUILTIN_PATTERNS_FILE = "builtin_patterns.json"
BUILTIN_THUMB_DIR = "builtin"
DEFAULT_SHAPE_FAMILY = "Arc"
# "original" keeps each shape's own per-point colors; a solid color overrides
# every lit point.
ORIGINAL_COLOR = "original"
SHAPE_COLOR_OPTIONS = [ORIGINAL_COLOR] + list(COLOR_OPTIONS)
DEFAULT_SHAPE_COLOR = ORIGINAL_COLOR
SVG_COLOR_OPTIONS = [ORIGINAL_COLOR] + list(COLOR_OPTIONS)
DEFAULT_SVG_COLOR = ORIGINAL_COLOR

# Firmware-native animation/effect families. These run inside projector
# firmware; HA sends only the selected one-based index and speed.
NATIVE_ANIMATION_FAMILIES = ("animation", "line", "christmas", "outdoor")
NATIVE_ANIMATION_COUNTS = {
    "animation": 50,
    "line": 50,
    "christmas": 50,
    "outdoor": 50,
}
NATIVE_ANIMATION_CATALOG_FILE = "native_animations.json"
NATIVE_ANIMATION_THUMB_DIR = "native"
DEFAULT_NATIVE_ANIMATION_FAMILY = "animation"
DEFAULT_NATIVE_ANIMATION_INDEX = 20
DEFAULT_NATIVE_ANIMATION_SPEED = 70
# Per-pattern loop-lock refresh overrides. Keep empty unless a pattern is proven
# to benefit from command refresh without visible restarts.
NATIVE_ANIMATION_LOOP_LOCKS = {}

# Sound-reactive ("Music") playback. The projector has an onboard microphone and
# a firmware sound-reactive mode: setting the C0 mode command's run-mode byte
# (field 9) to 255 makes whatever firmware effect is playing react to the room's
# sound instead of running at a fixed speed, and the sensitivity byte (field 10)
# sets the mic sensitivity. No host audio streaming is involved. Both settings
# are persisted in entry.options so they survive a restart.
DEFAULT_SOUND_REACTIVE = False
DEFAULT_SOUND_SENSITIVITY = 50
SOUND_SENSITIVITY_MIN = 1
SOUND_SENSITIVITY_MAX = 100

# Live effect transforms. The 16-byte config block at the head of every F0
# hand-draw command (cnfValus) carries firmware-driven geometric transforms; we
# apply them to our own SVG/shape/text draws. Model: each preset defines, per
# cnf index, the (slow, fast) band that the Motion speed slider sweeps -- speed
# 1 = the slow end, 100 = the fast end -- so one slider takes a preset from its
# slowest to its fastest. The displayed FX knobs are the resulting values, so
# they move with the speed slider. idx: 7=zoom 8=rotate_z 9=rotate_x 10=rotate_y
# 11=move_x 12=move_y. On this device_type=0 unit, rotate_z=vertical-axis spin,
# rotate_y=horizontal-axis spin (rotate bands: 128-191 forward, 192-255 reverse),
# move_x=barrel/cylinder warp, zoom(136-215)=loop scaling.
MOTION_PRESETS = {
    "off": {},
    "spin": {8: (128, 191)},                            # rotate_z forward spin
    "spin_reverse": {8: (192, 255)},                    # rotate_z reverse spin
    "flip": {10: (128, 255)},                           # rotate_y horizontal spin
    "tumble": {8: (128, 191), 10: (128, 255)},          # both axes -> 3D tumble
    "wobble": {9: (128, 255), 10: (128, 255)},          # rotate_x + rotate_y
    "cylinder": {11: (80, 255)},                        # move_x barrel/cylinder warp
    "throb": {7: (136, 215)},                           # zoom loop-scaling
    "chaos": {8: (128, 191), 10: (128, 255), 11: (80, 255)},  # everything at once
}
MOTION_MODES = tuple(MOTION_PRESETS)
MOTION_MODE_LABELS = {
    "off": "Off",
    "spin": "Spin",
    "spin_reverse": "Spin (reverse)",
    "flip": "Flip",
    "tumble": "Tumble",
    "wobble": "Wobble",
    "cylinder": "Cylinder",
    "throb": "Throb",
    "chaos": "Chaos",
}
MOTION_CUSTOM_LABEL = "Custom"

# Motion speed (1-100) sweeps each active field across its preset band:
# value = round(slow + (fast - slow) * (speed-1)/99). 1 = slowest, 100 = fastest.
MOTION_SPEED_MIN = 1
MOTION_SPEED_MAX = 100
DEFAULT_MOTION_SPEED = 50

# Raw transform "knobs" — the displayed/scaled draw-transform values. Full
# 0-255 range so EVERY behavior band is reachable (static position/warp AND
# continuous-motion speed). Motion presets populate the base and the speed
# slider scales these; hand-editing one makes the Motion picker read "Custom".
# (key, label, cnf_index). idx: 7=zoom 8=rotate_z 9=rotate_x 10=rotate_y
# 11=move_x 12=move_y.
TRANSFORM_KNOBS = (
    ("fx_zoom", "FX zoom (7)", 7),
    ("fx_rotate_z", "FX rotate-Z / vertical spin (8)", 8),
    ("fx_rotate_x", "FX rotate-X (9)", 9),
    ("fx_rotate_y", "FX rotate-Y / horizontal spin (10)", 10),
    ("fx_move_x", "FX move/warp-X (11)", 11),
    ("fx_move_y", "FX move/warp-Y (12)", 12),
)
TRANSFORM_KNOB_INDICES = tuple(index for *_, index in TRANSFORM_KNOBS)
FX_VALUE_MIN = 0
FX_VALUE_MAX = 255

# Host-side draw scale (percent) for SVG/shape/text. Multiplies the final draw
# points uniformly (x and y) -- a reliable static resize, since the firmware
# size/zoom fields don't scale cleanly on this unit. 100 = full auto-fit size,
# lower = smaller. Applied after the auto-fit-to-projector step.
DRAW_SCALE_MIN = 10
DRAW_SCALE_MAX = 100
DEFAULT_DRAW_SCALE = 100

# DMX-512 start address (base channel). Settable over BLE via the device
# settings block and read back from the device query. Only relevant when the
# laser is patched into a DMX universe (16-channel fixture).
DMX_ADDRESS_MIN = 1
DMX_ADDRESS_MAX = 512

# Projector mount-orientation setting values, not host-side coordinate
# transforms.
MOUNT_ORIENTATION_OPTIONS = {
    "Normal": 2,
    "Flip horizontal": 3,
    "Flip vertical": 1,
    "Rotate right 90": 5,
    "Rotate left 90": 7,
    "Rotate 180": 0,
}
MOUNT_ORIENTATION_BY_XY = {
    value: label for label, value in MOUNT_ORIENTATION_OPTIONS.items()
}

# Text display mode: "none" = static Hershey draw; "scroll" = firmware marquee
# (A0 packet + C0 mode 4 run-direction byte). Only horizontal (right-to-left)
# scroll works on this old device_type=0 unit; up/down need the device's
# vertical text layout (rotated glyphs + ver byte) which is not implemented, so
# they just fall back to right-to-left and are not offered.
SCROLL_DIRECTIONS = {"scroll": 255}
TEXT_MODES = ("none", "scroll")
DEFAULT_TEXT_MODE = "none"
DEFAULT_SCROLL_SPEED = 60
# Glyph scale for scrolling text. The device's text-scroll viewport is a fixed
# half-width central band (about 15.5 in vs 28 in for a full static draw) and does
# NOT scale with coordinates; unit 18 fits it well. Larger scales just make
# letters too big for that window so they break up (one char at a time).
SCROLL_UNIT = 18.0

# Vector text (Hershey) controls.
DEFAULT_TEXT_FONT = "Futural"
DEFAULT_TEXT_MESSAGE = "LAZERZ"
DEFAULT_TEXT_COLOR = "rainbow"
DEFAULT_TEXT_SIZE = 140  # cap height in projector units
DEFAULT_TEXT_Y = 0  # vertical center offset over the midline
TEXT_SIZE_MIN = 20
TEXT_SIZE_MAX = 400
TEXT_Y_MIN = -300
TEXT_Y_MAX = 300
# Projector drawable half-extent; text is auto-scaled to stay within this.
# Kept a little inside the true max so glyph detail near the edge does not hit
# the galvo's deflection limit.
PROJECTOR_LIMIT = 340
