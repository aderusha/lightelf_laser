"""Light entity for the LightElf Laser integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EytseLaserConfigEntry
from .entity import EytseLaserEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EytseLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the laser light entity."""
    async_add_entities([EytseLaserLight(config_entry.runtime_data)])


class EytseLaserLight(EytseLaserEntity, LightEntity):
    """Projector output power, reflecting the device's real on/off state."""

    _attr_name = None
    _attr_icon = "mdi:spotlight-beam"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, coordinator) -> None:
        """Initialize the light."""
        super().__init__(coordinator, "light")

    @property
    def available(self) -> bool:
        """Keep power control callable while HA is allowed to use Bluetooth."""
        data = self.coordinator.data or {}
        return bool(data.get("connection_enabled", self.coordinator.connection_enabled))

    @property
    def is_on(self) -> bool:
        """Return the real power state read from the device query."""
        return self.coordinator.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn projector output on."""
        await self.coordinator.async_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn projector output off."""
        await self.coordinator.async_power(False)
