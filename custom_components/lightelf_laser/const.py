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
