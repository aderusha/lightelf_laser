"""The LightElf Laser integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    COLOR_OPTIONS,
    DOMAIN,
    PLATFORMS,
    SHAPE_COLOR_OPTIONS,
    TEXT_COLOR_OPTIONS,
    TEXT_SIZE_MAX,
    TEXT_SIZE_MIN,
    TEXT_Y_MAX,
    TEXT_Y_MIN,
)
from .coordinator import EytseLaserConfigEntry, EytseLaserDataUpdateCoordinator
from .errors import LightElfLaserError

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_DRAW_SVG = "draw_svg"
SERVICE_DRAW_TEXT = "draw_text"
SERVICE_DRAW_SHAPE = "draw_shape"
SERVICE_PLAY_ANIMATION = "play_animation"
SERVICE_QUERY_DEVICE = "query_device"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-level services."""

    def _entry_from_call(call: ServiceCall) -> EytseLaserConfigEntry:
        entries = hass.config_entries.async_entries(DOMAIN)
        entry_id = call.data.get("entry_id")
        if entry_id:
            entries = [entry for entry in entries if entry.entry_id == entry_id]
        if not entries:
            raise HomeAssistantError("No LightElf Laser config entry is loaded")
        entry = entries[0]
        if entry.runtime_data is None:
            raise HomeAssistantError("LightElf Laser config entry is not ready")
        return entry

    async def _draw_svg(call: ServiceCall) -> None:
        coordinator = _entry_from_call(call).runtime_data
        if file := call.data.get("file"):
            await coordinator.async_rescan_svgs()
            if file not in coordinator.available_svgs:
                raise HomeAssistantError(
                    f"SVG {file!r} not found in {coordinator.svg_dir}"
                )
            coordinator.selected_svg = file
        try:
            await coordinator.async_display_svg()
        except LightElfLaserError as err:
            raise HomeAssistantError(str(err)) from err

    async def _draw_text(call: ServiceCall) -> None:
        coordinator = _entry_from_call(call).runtime_data
        if "text" in call.data:
            coordinator.text_message = call.data["text"]
        if font := call.data.get("font"):
            coordinator.text_font = font
        if color := call.data.get("color"):
            coordinator.text_color = color
        if "size" in call.data:
            coordinator.text_size = int(call.data["size"])
        if "vertical_position" in call.data:
            coordinator.text_y = int(call.data["vertical_position"])
        coordinator.async_update_listeners()
        try:
            await coordinator.async_display_text()
        except LightElfLaserError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_SVG,
        _draw_svg,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): str,
                vol.Optional("file"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_TEXT,
        _draw_text,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): str,
                vol.Optional("text"): cv.string,
                vol.Optional("font"): cv.string,
                vol.Optional("color"): vol.In(tuple(TEXT_COLOR_OPTIONS)),
                vol.Optional("size"): vol.All(
                    vol.Coerce(int), vol.Range(min=TEXT_SIZE_MIN, max=TEXT_SIZE_MAX)
                ),
                vol.Optional("vertical_position"): vol.All(
                    vol.Coerce(int), vol.Range(min=TEXT_Y_MIN, max=TEXT_Y_MAX)
                ),
            }
        ),
    )

    async def _draw_shape(call: ServiceCall) -> None:
        coordinator = _entry_from_call(call).runtime_data
        if family := call.data.get("family"):
            if family not in coordinator.builtin_families:
                raise HomeAssistantError(f"Unknown shape family {family!r}")
            coordinator.builtin_family = family
        if "index" in call.data:
            coordinator.builtin_index = max(
                0, min(int(call.data["index"]), coordinator.builtin_count - 1)
            )
        if color := call.data.get("color"):
            coordinator.builtin_color = color
        coordinator.async_update_listeners()
        try:
            await coordinator.async_display_shape()
        except LightElfLaserError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAW_SHAPE,
        _draw_shape,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): str,
                vol.Optional("family"): cv.string,
                vol.Optional("index"): vol.All(vol.Coerce(int), vol.Range(min=0)),
                vol.Optional("color"): vol.In(tuple(SHAPE_COLOR_OPTIONS)),
            }
        ),
    )

    async def _play_animation(call: ServiceCall) -> None:
        coordinator = _entry_from_call(call).runtime_data
        if family := call.data.get("family"):
            if family not in coordinator.native_animation_families:
                raise HomeAssistantError(f"Unknown animation family {family!r}")
            coordinator.native_animation_family = family
        if "index" in call.data:
            coordinator.native_animation_index = max(
                1,
                min(int(call.data["index"]), coordinator.native_animation_count),
            )
        if "speed" in call.data:
            coordinator.native_animation_speed = int(call.data["speed"])
        coordinator.async_update_listeners()
        try:
            await coordinator.async_display_native_animation()
        except LightElfLaserError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_PLAY_ANIMATION,
        _play_animation,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): str,
                vol.Optional("family"): cv.string,
                vol.Optional("index"): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional("speed"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            }
        ),
    )

    async def _query_device(call: ServiceCall) -> dict[str, Any]:
        coordinator = _entry_from_call(call).runtime_data
        try:
            result = await coordinator.client.request("query")
        except LightElfLaserError as err:
            raise HomeAssistantError(str(err)) from err
        return result.get("data", result)

    hass.services.async_register(
        DOMAIN,
        SERVICE_QUERY_DEVICE,
        _query_device,
        schema=vol.Schema({vol.Optional("entry_id"): str}),
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EytseLaserConfigEntry) -> bool:
    """Set up LightElf Laser from a config entry."""
    coordinator = EytseLaserDataUpdateCoordinator(hass, entry)
    await coordinator.async_load_fonts()
    await coordinator.async_load_builtin()
    await coordinator.async_load_native_animations()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
