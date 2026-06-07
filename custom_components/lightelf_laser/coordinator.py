"""Data coordinator for the LightElf Laser integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
import os
from pathlib import Path
import shutil
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bluetooth_client import LightElfBluetoothClient
from .const import (
    BUILTIN_PATTERNS_FILE,
    BUILTIN_THUMB_DIR,
    COLOR_OPTIONS,
    CONF_TIMEOUT,
    DEFAULT_DRAW_SCALE,
    DEFAULT_MOTION_SPEED,
    DEFAULT_NATIVE_ANIMATION_FAMILY,
    DEFAULT_NATIVE_ANIMATION_INDEX,
    DEFAULT_NATIVE_ANIMATION_SPEED,
    DEFAULT_SCROLL_SPEED,
    DEFAULT_SVG_COLOR,
    DEFAULT_TEXT_MODE,
    DEFAULT_SHAPE_COLOR,
    DEFAULT_TEXT_MESSAGE,
    DEFAULT_SHAPE_FAMILY,
    DEFAULT_SOUND_REACTIVE,
    DEFAULT_SOUND_SENSITIVITY,
    DEFAULT_TEXT_COLOR,
    DEFAULT_TEXT_FONT,
    DEFAULT_TEXT_SIZE,
    DEFAULT_TEXT_Y,
    DEFAULT_TIMEOUT,
    DOMAIN,
    DRAW_SCALE_MAX,
    DRAW_SCALE_MIN,
    FX_VALUE_MAX,
    FX_VALUE_MIN,
    LOGGER,
    MOTION_PRESETS,
    MOTION_SPEED_MAX,
    MOTION_SPEED_MIN,
    MOUNT_ORIENTATION_BY_XY,
    MOUNT_ORIENTATION_OPTIONS,
    NATIVE_ANIMATION_CATALOG_FILE,
    NATIVE_ANIMATION_COUNTS,
    NATIVE_ANIMATION_LOOP_LOCKS,
    NATIVE_ANIMATION_THUMB_DIR,
    PROJECTOR_LIMIT,
    SCROLL_DIRECTIONS,
    SCROLL_UNIT,
    SOUND_SENSITIVITY_MAX,
    SOUND_SENSITIVITY_MIN,
    STARTER_SVG_DIR,
    SVG_LEGACY_SUBDIR,
    SVG_MEDIA_SUBDIR,
    TRANSFORM_KNOB_INDICES,
    TRANSPORT_BLUETOOTH,
    UPDATE_INTERVAL,
)
from .errors import LightElfLaserError
from .hershey import list_fonts, render_text_segments
from .preview import colorize_text_segments, render_segments_png
from .protocol import draw_points_command, mode_command, segments_to_points
from .scroll_text import build_scroll_a0
from .svg import read_svg, svg_draw_command, transform_segments

_COMPONENT_DIR = Path(__file__).parent

# Max points per draw frame. Unacked writes are paced ~30 ms apart for ordering
# (see bluetooth_client), so the whole frame must still land inside the device's
# frame-assembly window or the tail is dropped. ~160 points keeps transmission
# near ~1.2 s. Denser frames are thinned stroke-aware (pen-up points preserved).
DRAW_POINT_BUDGET = 160


def _xy_from_invert_switches(invert_x: bool, invert_y: bool) -> int:
    """Map simple HA X/Y inversion switches to projector orientation values."""
    if invert_x and invert_y:
        return MOUNT_ORIENTATION_OPTIONS["Rotate 180"]
    if invert_x:
        return MOUNT_ORIENTATION_OPTIONS["Flip horizontal"]
    if invert_y:
        return MOUNT_ORIENTATION_OPTIONS["Flip vertical"]
    return MOUNT_ORIENTATION_OPTIONS["Normal"]


def _xy_inverts_x(xy: int) -> bool:
    """Return whether the projector orientation has negative X orientation."""
    return xy in (0, 3, 7)


def _xy_inverts_y(xy: int) -> bool:
    """Return whether the projector orientation has negative Y orientation."""
    return xy in (0, 1, 5)


def _rainbow_recolor(points: list[list[int]]) -> list[list[int]]:
    """Cycle lit-point colors 1..7 per stroke (travel points stay color 0)."""
    out: list[list[int]] = []
    color = 6
    for point in points:
        if int(point[2]) == 0:
            color = 1 if color >= 7 else color + 1
            out.append([point[0], point[1], 0, point[3]])
        else:
            out.append([point[0], point[1], color, point[3]])
    return out


def _fit_point_budget(points: list[list[int]], budget: int) -> list[list[int]]:
    """Thin a point frame to <= budget, preserving stroke structure.

    Keeps every travel point (color 0), each stroke's first and last lit point,
    and the final point; thins only interior lit points by even sampling.
    """
    count = len(points)
    if count <= budget:
        return points
    mandatory: set[int] = {0, count - 1}
    for index, point in enumerate(points):
        if int(point[2]) == 0:
            mandatory.add(index)
            if index > 0:
                mandatory.add(index - 1)  # last lit point of the previous stroke
            if index + 1 < count:
                mandatory.add(index + 1)  # first lit point of the next stroke
    optional = [index for index in range(count) if index not in mandatory]
    keep = budget - len(mandatory)
    if keep <= 0:
        chosen = set(mandatory)
    else:
        step = len(optional) / keep
        chosen = set(mandatory) | {optional[int(k * step)] for k in range(keep)}
    return [points[index] for index in sorted(chosen)]

type EytseLaserConfigEntry = ConfigEntry[EytseLaserDataUpdateCoordinator]


class EytseLaserDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hold connection state, real power state, and the SVG file list."""

    config_entry: EytseLaserConfigEntry

    def __init__(self, hass: HomeAssistant, entry: EytseLaserConfigEntry) -> None:
        """Initialize the coordinator."""
        self.transport = entry.data.get("transport", TRANSPORT_BLUETOOTH)
        timeout = float(entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
        self.client = LightElfBluetoothClient(hass, entry.data[CONF_ADDRESS], timeout)

        # Whether HA should hold the BLE connection (and poll). When False the
        # radio is released so another BLE controller can take the single slot.
        # Persisted in entry.options so a restart doesn't grab the radio back.
        self.connection_enabled = bool(entry.options.get("connection_enabled", True))
        self.is_on = False

        # SVG upload folder + picker state. Prefer Home Assistant's local media
        # tree so users can upload through the built-in media/file browser.
        self.svg_dir = self._resolve_svg_media_dir(hass)
        self.svg_legacy_dir = Path(hass.config.path(SVG_LEGACY_SUBDIR))
        self.available_svgs: list[str] = []
        self.selected_svg: str | None = None

        # Vector text state.
        self.available_fonts: list[str] = []
        self.text_message = DEFAULT_TEXT_MESSAGE
        self.text_font = DEFAULT_TEXT_FONT
        self.text_color = DEFAULT_TEXT_COLOR
        self.text_size = DEFAULT_TEXT_SIZE
        self.text_y = DEFAULT_TEXT_Y

        # SVG color override. "original" preserves per-stroke colors from the
        # uploaded SVG; choosing a beam color forces all lit SVG strokes to it.
        self.svg_color = DEFAULT_SVG_COLOR

        # Text display mode (none = static draw; others scroll) + scroll speed.
        self.text_mode = DEFAULT_TEXT_MODE
        self.scroll_speed = DEFAULT_SCROLL_SPEED

        # Built-in shape library state.
        self._builtin_frames: dict[str, list[list[list[int]]]] = {}
        self.builtin_families: list[str] = []
        self.builtin_family = DEFAULT_SHAPE_FAMILY
        self.builtin_index = 0
        self.builtin_color = DEFAULT_SHAPE_COLOR

        # Firmware-native animation state. Index is one-based, matching the
        # projector's C0 project selection byte.
        self.native_animation_families = list(NATIVE_ANIMATION_COUNTS)
        self.native_animation_family = DEFAULT_NATIVE_ANIMATION_FAMILY
        self.native_animation_index = DEFAULT_NATIVE_ANIMATION_INDEX
        self.native_animation_speed = DEFAULT_NATIVE_ANIMATION_SPEED
        self._native_animation_catalog: dict[str, dict[int, dict[str, Any]]] = {}

        # Sound-reactive ("Music") playback. When enabled, firmware effects react
        # to the projector's onboard microphone instead of a fixed speed; the
        # sensitivity sets the mic gain. Both persist in entry.options. The active
        # flag tracks whether the last thing displayed is a firmware effect, so
        # toggling sound mode can re-apply it live without clobbering a static
        # SVG/shape/text draw.
        self.sound_reactive = bool(
            entry.options.get("sound_reactive", DEFAULT_SOUND_REACTIVE)
        )
        self.sound_sensitivity = int(
            entry.options.get("sound_sensitivity", DEFAULT_SOUND_SENSITIVITY)
        )
        self._native_animation_active = False

        # Live effect transforms applied to our own draws (SVG/shape/text). A
        # motion preset selects which cnf fields are active and their (slow,fast)
        # bands; the Motion speed slider sweeps the bands. The displayed FX knobs
        # are the resulting values, so they move with the speed slider. Editing a
        # knob switches to "custom" (literal per-knob values). Persisted in
        # entry.options (motion_mode + motion_speed + motion_custom). The
        # last-draw callback lets a preset/speed/knob change re-issue the current
        # draw live.
        self.motion_mode = str(entry.options.get("motion_mode", "off"))
        self.motion_speed = int(entry.options.get("motion_speed", DEFAULT_MOTION_SPEED))
        stored_custom = entry.options.get("motion_custom", {}) or {}
        self.motion_custom = {
            index: int(stored_custom.get(str(index), 0)) for index in TRANSFORM_KNOB_INDICES
        }
        # Host-side static draw scale (percent); shrinks SVG/shape/text uniformly.
        self.draw_scale = int(entry.options.get("draw_scale", DEFAULT_DRAW_SCALE))
        self._last_draw: Callable[[], Awaitable[None]] | None = None

        # Projector-global mount orientation. This xy byte controls normal,
        # flipped, and 90-degree rotated output and is read back from query.
        self.mount_xy = MOUNT_ORIENTATION_OPTIONS["Normal"]

        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=UPDATE_INTERVAL,
        )

    @property
    def device_id(self) -> str:
        """Stable device identifier."""
        return self.client.device_id

    # -- SVG folder ---------------------------------------------------------

    @staticmethod
    def _resolve_svg_media_dir(hass: HomeAssistant) -> Path:
        """Return the local-media SVG upload directory for this HA install."""
        media_root = Path("/media")
        if media_root.exists():
            return media_root / SVG_MEDIA_SUBDIR
        media_dirs = getattr(hass.config, "media_dirs", {}) or {}
        local_media = media_dirs.get("local") if isinstance(media_dirs, dict) else None
        if local_media:
            return Path(local_media) / SVG_MEDIA_SUBDIR
        return Path(hass.config.path("media")) / SVG_MEDIA_SUBDIR

    def _migrate_legacy_svgs(self) -> None:
        """Copy old config-dir SVG drops into the media upload directory."""
        if self.svg_legacy_dir.resolve() == self.svg_dir.resolve():
            return
        if not self.svg_legacy_dir.exists():
            return
        try:
            self.svg_dir.mkdir(parents=True, exist_ok=True)
            for path in self.svg_legacy_dir.glob("*.svg"):
                target = self.svg_dir / path.name
                if not target.exists():
                    shutil.copy2(path, target)
        except OSError as err:
            LOGGER.warning(
                "Could not migrate SVG files from %s to %s: %s",
                self.svg_legacy_dir,
                self.svg_dir,
                err,
            )

    def _seed_starter_svgs(self) -> None:
        """Copy bundled starter SVGs into local media without overwriting."""
        starter_dir = _COMPONENT_DIR / STARTER_SVG_DIR
        if not starter_dir.exists():
            return
        for path in starter_dir.glob("*.svg"):
            target = self.svg_dir / path.name
            if not target.exists():
                shutil.copy2(path, target)

    def _scan_svg_dir(self) -> list[str]:
        """List *.svg files in the drop folder (executor context)."""
        try:
            self.svg_dir.mkdir(parents=True, exist_ok=True)
            self._migrate_legacy_svgs()
            self._seed_starter_svgs()
            names = [
                name
                for name in os.listdir(self.svg_dir)
                if name.lower().endswith(".svg")
                and (self.svg_dir / name).is_file()
            ]
        except OSError as err:
            LOGGER.warning("Could not read SVG folder %s: %s", self.svg_dir, err)
            return []
        return sorted(names, key=str.lower)

    async def async_rescan_svgs(self) -> None:
        """Refresh the available SVG list and keep the selection valid."""
        self.available_svgs = await self.hass.async_add_executor_job(self._scan_svg_dir)
        if self.selected_svg not in self.available_svgs:
            self.selected_svg = self.available_svgs[0] if self.available_svgs else None
        self.async_update_listeners()

    # -- fonts --------------------------------------------------------------

    async def async_load_fonts(self) -> None:
        """Load the bundled Hershey font list and keep the selection valid."""
        self.available_fonts = await self.hass.async_add_executor_job(list_fonts)
        if self.text_font not in self.available_fonts:
            self.text_font = (
                DEFAULT_TEXT_FONT
                if DEFAULT_TEXT_FONT in self.available_fonts
                else (self.available_fonts[0] if self.available_fonts else DEFAULT_TEXT_FONT)
            )

    # -- built-in shapes ----------------------------------------------------

    def _load_builtin_blocking(self) -> tuple[list[str], dict[str, list]]:
        """Read the bundled built-in shape catalog (executor context)."""
        path = _COMPONENT_DIR / BUILTIN_PATTERNS_FILE
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        families: list[str] = []
        frames: dict[str, list] = {}
        for family in data.get("families", []):
            name = family["label_en"]
            families.append(name)
            frames[name] = family["frames"]
        return families, frames

    async def async_load_builtin(self) -> None:
        """Load the built-in shape catalog and validate the selection."""
        self.builtin_families, self._builtin_frames = (
            await self.hass.async_add_executor_job(self._load_builtin_blocking)
        )
        if self.builtin_family not in self.builtin_families:
            self.builtin_family = (
                self.builtin_families[0] if self.builtin_families else DEFAULT_SHAPE_FAMILY
            )
        self.builtin_index = min(self.builtin_index, self.builtin_count - 1)

    @property
    def builtin_count(self) -> int:
        """Number of shapes in the selected family."""
        return len(self._builtin_frames.get(self.builtin_family, [])) or 1

    @property
    def builtin_thumb_path(self) -> Path:
        """Filesystem path to the selected shape's thumbnail."""
        return (
            _COMPONENT_DIR
            / BUILTIN_THUMB_DIR
            / f"{self.builtin_family}_{self.builtin_index:03d}.png"
        )

    def _read_thumb_blocking(self) -> bytes | None:
        try:
            return self.builtin_thumb_path.read_bytes()
        except OSError:
            return None

    async def async_read_shape_thumb(self) -> bytes | None:
        """Return PNG bytes for the currently-selected shape (executor)."""
        return await self.hass.async_add_executor_job(self._read_thumb_blocking)

    # -- local SVG/text previews ------------------------------------------

    def _build_svg_preview_blocking(self) -> bytes | None:
        """Render the selected SVG to a local PNG preview."""
        if not self.selected_svg:
            return None
        path = self.svg_dir / self.selected_svg
        try:
            drawing = read_svg(str(path))
        except Exception as err:
            LOGGER.warning("Could not render SVG preview for %s: %s", path, err)
            return None
        segments = transform_segments(drawing, size=640)
        if self.svg_color != "original":
            color_id = COLOR_OPTIONS.get(self.svg_color, 5)
            segments = [
                [[point[0], point[1], color_id] for point in segment]
                for segment in segments
            ]
        return render_segments_png(segments)

    async def async_read_svg_preview(self) -> bytes | None:
        """Return PNG bytes for the currently-selected SVG preview."""
        return await self.hass.async_add_executor_job(self._build_svg_preview_blocking)

    def _build_text_preview_blocking(self) -> bytes | None:
        """Render the current text settings to a local PNG preview."""
        message = (self.text_message or "").strip()
        if not message:
            return render_segments_png([])
        try:
            segments = render_text_segments(
                message,
                self.text_font,
                height=int(self.text_size),
                y=int(self.text_y),
            )
        except Exception as err:
            LOGGER.warning("Could not render text preview: %s", err)
            return None
        if not segments:
            return None

        xs = [point[0] for stroke in segments for point in stroke]
        ys = [point[1] for stroke in segments for point in stroke]
        max_x = max(abs(min(xs)), abs(max(xs))) or 1.0
        max_y = max(abs(min(ys)), abs(max(ys))) or 1.0
        scale = min(1.0, PROJECTOR_LIMIT / max_x, PROJECTOR_LIMIT / max_y)
        fitted = [
            [[point[0] * scale, point[1] * scale] for point in stroke]
            for stroke in segments
        ]
        color_id = None if self.text_color == "rainbow" else COLOR_OPTIONS.get(self.text_color, 5)
        return render_segments_png(colorize_text_segments(fitted, color_id))

    async def async_read_text_preview(self) -> bytes | None:
        """Return PNG bytes for the current text preview."""
        return await self.hass.async_add_executor_job(self._build_text_preview_blocking)

    # -- firmware-native animations ---------------------------------------

    def _load_native_animation_catalog_blocking(self) -> dict[str, dict[int, dict[str, Any]]]:
        """Read captured native animation thumbnail metadata, if bundled."""
        path = _COMPONENT_DIR / NATIVE_ANIMATION_CATALOG_FILE
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        out: dict[str, dict[int, dict[str, Any]]] = {}
        for family, items in data.get("families", {}).items():
            out[family] = {
                int(item["index"]): item
                for item in items
                if "index" in item
            }
        return out

    async def async_load_native_animations(self) -> None:
        """Load native animation thumbnail metadata and validate selection."""
        self._native_animation_catalog = await self.hass.async_add_executor_job(
            self._load_native_animation_catalog_blocking
        )
        if self.native_animation_family not in self.native_animation_families:
            self.native_animation_family = DEFAULT_NATIVE_ANIMATION_FAMILY
        self.native_animation_index = max(
            1,
            min(self.native_animation_index, self.native_animation_count),
        )

    @property
    def native_animation_count(self) -> int:
        """Number of selectable native animations in the selected family."""
        return NATIVE_ANIMATION_COUNTS.get(self.native_animation_family, 64)

    @property
    def native_animation_thumb_path(self) -> Path | None:
        """Filesystem path to the captured preview for the selected native animation."""
        item = self._native_animation_catalog.get(self.native_animation_family, {}).get(
            self.native_animation_index
        )
        if not item:
            return None
        raw = (
            item.get("animated_thumb")
            or item.get("contact_strip")
            or item.get("flat_thumb")
            or item.get("thumb")
        )
        if not raw:
            return None
        return _COMPONENT_DIR / NATIVE_ANIMATION_THUMB_DIR / Path(str(raw)).name

    def _read_native_animation_thumb_blocking(self) -> bytes | None:
        path = self.native_animation_thumb_path
        if path is None:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    async def async_read_native_animation_thumb(self) -> bytes | None:
        """Return captured preview bytes for the current native animation."""
        return await self.hass.async_add_executor_job(
            self._read_native_animation_thumb_blocking
        )

    @property
    def mount_orientation(self) -> str:
        """Current mount-orientation label."""
        return MOUNT_ORIENTATION_BY_XY.get(self.mount_xy, f"Custom ({self.mount_xy})")

    @property
    def invert_x(self) -> bool:
        """Whether the current mount orientation flips the X axis."""
        return _xy_inverts_x(self.mount_xy)

    @property
    def invert_y(self) -> bool:
        """Whether the current mount orientation flips the Y axis."""
        return _xy_inverts_y(self.mount_xy)

    async def async_set_mount_xy(self, xy: int) -> None:
        """Update the projector's global mount orientation setting."""
        xy = int(xy)
        response = await self.client.request("settings", {"xy": xy})
        data = response.get("data") or {}
        self.mount_xy = int(data.get("xy", xy))
        self.async_set_updated_data(
            {
                **(self.data or {}),
                "connection_enabled": self.connection_enabled,
                "connected": True,
                "can_send": True,
                "available": True,
                "mount_xy": self.mount_xy,
            }
        )
        await self.async_request_refresh()

    async def async_set_invert_x(self, enabled: bool) -> None:
        """Toggle X inversion using the non-rotated orientation presets."""
        await self.async_set_mount_xy(_xy_from_invert_switches(enabled, self.invert_y))

    async def async_set_invert_y(self, enabled: bool) -> None:
        """Toggle Y inversion using the non-rotated orientation presets."""
        await self.async_set_mount_xy(_xy_from_invert_switches(self.invert_x, enabled))

    async def async_display_native_animation(self) -> None:
        """Play the selected firmware-native animation (powers on)."""
        lock_interval = NATIVE_ANIMATION_LOOP_LOCKS.get(
            (self.native_animation_family, self.native_animation_index)
        )
        await self.client.request("power", {"on": True})
        await self.client.request(
            "builtin_native",
            {
                "family": self.native_animation_family,
                "pattern": self.native_animation_index,
                "speed": self.native_animation_speed,
                "playback": "sound" if self.sound_reactive else "auto",
                "sound_percent": self.sound_sensitivity,
                "loop": lock_interval is not None,
                "lock_interval": lock_interval or 0.75,
            },
        )
        self.is_on = True
        self._native_animation_active = True
        self._last_draw = None
        await self.async_request_refresh()

    async def async_display_shape(self) -> None:
        """Draw the selected built-in shape as a static frame (powers on)."""
        frame = self._builtin_frames.get(self.builtin_family, [])
        if not frame or not 0 <= self.builtin_index < len(frame):
            raise LightElfLaserError("No built-in shape selected")
        points = frame[self.builtin_index]
        # None -> preserve the shape's own per-point colors; else force one color.
        color_id = None if self.builtin_color == "original" else COLOR_OPTIONS.get(self.builtin_color, 5)
        command = await self.hass.async_add_executor_job(
            self._build_shape_command,
            points,
            color_id,
            self._motion_cnf_values(),
            self.draw_scale_factor,
        )
        await self.client.request("power", {"on": True})
        await self.client.request("raw", {"hex": command})
        self.is_on = True
        self._native_animation_active = False
        self._last_draw = self.async_display_shape
        await self.async_request_refresh()

    @staticmethod
    def _build_shape_command(
        points: list[list[int]],
        color_id: int | None,
        cnf_values: list[int] | None = None,
        scale: float = 1.0,
    ) -> str:
        """Fit a built-in frame to the projector and build the draw command.

        ``color_id`` None preserves each point's own color (most built-in shapes
        are multi-colored); a value forces every lit point to that single color.
        Color 0 = travel/pen-up either way. The few stray
        color values outside 1-7 are folded back into the 1-7 palette.
        """
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        max_x = max(abs(min(xs)), abs(max(xs))) or 1
        max_y = max(abs(min(ys)), abs(max(ys))) or 1
        fit = min(1.0, PROJECTOR_LIMIT / max_x, PROJECTOR_LIMIT / max_y)

        def out_color(raw: int) -> int:
            if raw == 0:
                return 0  # travel / pen-up
            if color_id is not None:
                return color_id
            return raw if 1 <= raw <= 7 else ((raw - 1) % 7) + 1

        recolored = [
            [round(p[0] * fit), round(p[1] * fit), out_color(int(p[2])), 0]
            for p in points
        ]
        recolored = _fit_point_budget(recolored, DRAW_POINT_BUDGET)
        return draw_points_command(
            recolored, cnf_values=cnf_values, cmd_new_type=False, scale=scale
        )

    # -- coordinator update -------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll connection/power state when connected; always refresh SVGs."""
        self.available_svgs = await self.hass.async_add_executor_job(self._scan_svg_dir)
        if self.selected_svg not in self.available_svgs:
            self.selected_svg = self.available_svgs[0] if self.available_svgs else None

        if not self.connection_enabled:
            return {
                "connection_enabled": False,
                "connected": False,
                "can_send": False,
                "available": False,
            }

        try:
            response = await self.client.request("query")
        except LightElfLaserError as err:
            LOGGER.debug("LightElf query failed: %s", err)
            return {
                "connection_enabled": True,
                "connected": False,
                "can_send": False,
                "available": False,
                "error": str(err),
            }
        except Exception as err:
            LOGGER.debug("LightElf query failed unexpectedly: %s", err, exc_info=True)
            return {
                "connection_enabled": True,
                "connected": False,
                "can_send": False,
                "available": False,
                "error": str(err),
            }

        data = response.get("data") or {}
        device_on = bool(data.get("device_on", self.is_on))
        if data.get("settings_xy") is not None:
            self.mount_xy = int(data["settings_xy"])
        mode_state = data.get("mode_state")
        self.is_on = device_on
        return {
            "connection_enabled": True,
            "connected": True,
            "can_send": True,
            "available": True,
            "device_on": device_on,
            "mount_xy": self.mount_xy,
            "mode_state": mode_state,
        }

    # -- control actions ----------------------------------------------------

    async def async_set_connection(self, enabled: bool) -> None:
        """Hold or release the BLE connection (persisted across restarts)."""
        self.connection_enabled = enabled
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={**self.config_entry.options, "connection_enabled": enabled},
        )
        if enabled:
            await self.client.request("ble_connect")
        else:
            await self.client.request("ble_release")
        await self.async_request_refresh()

    async def async_set_sound_reactive(self, enabled: bool) -> None:
        """Enable/disable sound-reactive ("Music") firmware playback.

        Persisted in entry.options. If a firmware effect is currently playing,
        the selected animation is re-issued so the new mode takes effect live.
        Static SVG/shape/text draws are left untouched.
        """
        self.sound_reactive = bool(enabled)
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={**self.config_entry.options, "sound_reactive": self.sound_reactive},
        )
        await self._reapply_sound_if_playing()
        self.async_update_listeners()

    async def async_set_sound_sensitivity(self, value: int) -> None:
        """Set the onboard-mic sensitivity (1-100) for sound-reactive playback."""
        self.sound_sensitivity = max(
            SOUND_SENSITIVITY_MIN, min(SOUND_SENSITIVITY_MAX, int(value))
        )
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={
                **self.config_entry.options,
                "sound_sensitivity": self.sound_sensitivity,
            },
        )
        # Sensitivity only matters while sound mode is on; re-apply if reactive.
        if self.sound_reactive:
            await self._reapply_sound_if_playing()
        self.async_update_listeners()

    async def _reapply_sound_if_playing(self) -> None:
        """Re-issue the current firmware animation so sound settings take effect."""
        if self.is_on and self._native_animation_active and self.connection_enabled:
            await self.async_display_native_animation()

    def _scale_band(self, band: tuple[int, int]) -> int:
        """Map the motion speed (1-100) into a (slow, fast) band."""
        low, high = band
        frac = (max(MOTION_SPEED_MIN, min(MOTION_SPEED_MAX, self.motion_speed)) - 1) / 99
        return max(FX_VALUE_MIN, min(FX_VALUE_MAX, round(low + (high - low) * frac)))

    @property
    def fx_values(self) -> dict[int, int]:
        """The displayed/sent knob values for the current mode + speed."""
        if self.motion_mode == "custom":
            return {i: int(self.motion_custom.get(i, 0)) for i in TRANSFORM_KNOB_INDICES}
        preset = MOTION_PRESETS.get(self.motion_mode, {})
        return {
            i: (self._scale_band(preset[i]) if i in preset else 0)
            for i in TRANSFORM_KNOB_INDICES
        }

    def _motion_cnf_values(self) -> list[int] | None:
        """Build the F0 config-block transform from the current knob values.

        Returns a 13-int cnf_values list, or None when all knobs are zero.
        Applied to our own SVG/shape/text draws to make them move.
        """
        fx = self.fx_values
        if not any(fx.values()):
            return None
        cnf = [0] * 13
        for index in TRANSFORM_KNOB_INDICES:
            cnf[index] = fx[index]
        return cnf

    @property
    def motion_preset(self) -> str | None:
        """Current preset name, or None when in custom mode."""
        return self.motion_mode if self.motion_mode in MOTION_PRESETS else None

    async def async_set_motion(self, mode: str) -> None:
        """Select a motion preset; the speed slider then sweeps its band."""
        if mode not in MOTION_PRESETS:
            raise LightElfLaserError(f"unknown motion preset {mode!r}")
        self.motion_mode = mode
        self._persist_motion()
        await self._reapply_motion_if_drawing()
        self.async_update_listeners()

    def _persist_motion(self) -> None:
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={
                **self.config_entry.options,
                "motion_mode": self.motion_mode,
                "motion_speed": self.motion_speed,
                "motion_custom": {str(i): v for i, v in self.motion_custom.items()},
            },
        )

    async def async_set_fx(self, index: int, value: int) -> None:
        """Set a knob directly (0-255) -> custom mode, with the rest snapshotted."""
        value = max(FX_VALUE_MIN, min(FX_VALUE_MAX, int(value)))
        self.motion_custom = dict(self.fx_values)
        self.motion_custom[index] = value
        self.motion_mode = "custom"
        self._persist_motion()
        await self._reapply_motion_if_drawing()
        self.async_update_listeners()

    async def async_set_motion_speed(self, value: int) -> None:
        """Set the motion speed (1-100); sweeps preset bands, re-applies live."""
        self.motion_speed = max(MOTION_SPEED_MIN, min(MOTION_SPEED_MAX, int(value)))
        self._persist_motion()
        await self._reapply_motion_if_drawing()
        self.async_update_listeners()

    @property
    def draw_scale_factor(self) -> float:
        """Current host-side draw scale as a 0.1-1.0 multiplier."""
        return max(DRAW_SCALE_MIN, min(DRAW_SCALE_MAX, self.draw_scale)) / 100

    async def async_set_draw_scale(self, value: int) -> None:
        """Set the host-side draw scale (percent) and re-apply the current draw."""
        self.draw_scale = max(DRAW_SCALE_MIN, min(DRAW_SCALE_MAX, int(value)))
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={**self.config_entry.options, "draw_scale": self.draw_scale},
        )
        await self._reapply_motion_if_drawing()
        self.async_update_listeners()

    async def _reapply_motion_if_drawing(self) -> None:
        """Re-issue the last SVG/shape/text draw so a motion change shows live."""
        if self.is_on and self._last_draw is not None and self.connection_enabled:
            await self._last_draw()

    async def async_power(self, on: bool) -> None:
        """Turn laser output on or off."""
        if on:
            await self.client.request("power", {"on": True})
        else:
            # Use the same raw old-protocol OFF packet that is live-verified to
            # stop native animations and update the real device_on byte.
            await self.client.request("raw", {"hex": "B0B1B2B300B4B5B6B7"})
            self._native_animation_active = False
            self._last_draw = None
        self.is_on = on
        self.async_set_updated_data(
            {
                **(self.data or {}),
                "connection_enabled": self.connection_enabled,
                "connected": True,
                "can_send": True,
                "available": True,
                "device_on": on,
            }
        )
        await self.async_request_refresh()

    async def async_display_svg(self) -> None:
        """Draw the selected SVG (powering the laser on first)."""
        if not self.selected_svg:
            raise LightElfLaserError("No SVG is selected")
        path = str(self.svg_dir / self.selected_svg)
        color_id = None if self.svg_color == "original" else COLOR_OPTIONS.get(self.svg_color, 5)
        command = await self.hass.async_add_executor_job(
            self._build_svg_command,
            path,
            color_id,
            self._motion_cnf_values(),
            self.draw_scale_factor,
        )
        await self.client.request("power", {"on": True})
        await self.client.request("raw", {"hex": command})
        self.is_on = True
        self._native_animation_active = False
        self._last_draw = self.async_display_svg
        await self.async_request_refresh()

    @staticmethod
    def _build_svg_command(
        path: str,
        color_id: int | None,
        cnf_values: list[int] | None = None,
        scale: float = 1.0,
    ) -> str:
        """Convert an SVG file to an F0/F4 draw command (executor context)."""
        # Keep the point budget transmission-safe (see DRAW_POINT_BUDGET); the
        # SVG path has its own geometry-aware simplification to hit it.
        return svg_draw_command(
            path,
            max_points=DRAW_POINT_BUDGET,
            override_color=color_id,
            cmd_new_type=False,
            cnf_values=cnf_values,
            scale=scale,
        )

    async def async_display_text(self) -> None:
        """Display the current text: static draw, or firmware scroll by mode."""
        if self.text_mode == "none":
            await self._display_static_text()
        else:
            await self._display_scroll_text(SCROLL_DIRECTIONS.get(self.text_mode, 255))

    async def _display_static_text(self) -> None:
        """Render the current text as Hershey strokes and draw it (powers on)."""
        message = (self.text_message or "").strip()
        if not message:
            raise LightElfLaserError("No text to display")
        # color_id None -> rainbow (cycle per stroke), else a single color index.
        color_id = None if self.text_color == "rainbow" else COLOR_OPTIONS.get(self.text_color, 5)
        command = await self.hass.async_add_executor_job(
            self._build_text_command,
            message,
            self.text_font,
            int(self.text_size),
            color_id,
            int(self.text_y),
            self._motion_cnf_values(),
            self.draw_scale_factor,
        )
        await self.client.request("power", {"on": True})
        await self.client.request("raw", {"hex": command})
        self.is_on = True
        self._native_animation_active = False
        self._last_draw = self.async_display_text
        await self.async_request_refresh()

    @staticmethod
    def _build_text_command(
        text: str,
        font: str,
        size: int,
        color_id: int | None,
        text_y: int,
        cnf_values: list[int] | None = None,
        scale: float = 1.0,
    ) -> str:
        """Render Hershey text to an F0/F4 draw command (executor context).

        Text is auto-scaled down so it never runs off the projector's drawable
        area, then shifted vertically by ``text_y`` (over the midline).
        ``color_id`` None -> rainbow (cycle per stroke), else a single color.
        """
        segments = render_text_segments(text, font, height=size)
        if not segments:
            raise LightElfLaserError("Text produced no drawable strokes")

        xs = [point[0] for stroke in segments for point in stroke]
        ys = [point[1] for stroke in segments for point in stroke]
        max_x = max(abs(min(xs)), abs(max(xs))) or 1.0
        max_y = max(abs(min(ys)), abs(max(ys))) or 1.0
        fit = min(1.0, PROJECTOR_LIMIT / max_x, PROJECTOR_LIMIT / max_y)

        fitted = [
            [[point[0] * fit, point[1] * fit + text_y] for point in stroke]
            for stroke in segments
        ]
        points = segments_to_points(fitted, color=color_id or 7, steps_per_segment=2)
        points = _fit_point_budget(points, DRAW_POINT_BUDGET)
        if color_id is None:
            points = _rainbow_recolor(points)
        return draw_points_command(
            points, cnf_values=cnf_values, cmd_new_type=False, scale=scale
        )

    async def _display_scroll_text(self, direction: int) -> None:
        """Marquee the current text via firmware scrolling (powers on).

        Sends the A0 text packet first (loads the text), THEN the C0 mode-4
        command with run direction + speed (triggers the firmware scroll). That
        order matters: C0 first scrolls the device's previously-stored text.
        Colors cycle per stroke (rainbow), matching the app. Uses a fixed,
        proven glyph scale (SCROLL_UNIT) so coordinates stay in device range.
        """
        message = (self.text_message or "").strip()
        if not message:
            raise LightElfLaserError("No text to scroll")
        solid = None if self.text_color == "rainbow" else COLOR_OPTIONS.get(self.text_color, 5)
        a0 = await self.hass.async_add_executor_job(
            build_scroll_a0, message, self.text_font, SCROLL_UNIT, 5, solid
        )
        c0 = mode_command(
            mode=4,
            color=9,
            size_percent=100,
            speed_percent=int(self.scroll_speed),
            distance_percent=50,
            run_direction=direction,
            arb_play=True,
        )
        await self.client.request("power", {"on": True})
        await self.client.request("raw", {"hex": a0})
        await self.client.request("raw", {"hex": c0})
        self.is_on = True
        self._native_animation_active = False
        self._last_draw = None
        await self.async_request_refresh()
