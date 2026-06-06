"""Switch entities for the LightElf Laser integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EytseLaserConfigEntry
from .entity import EytseLaserEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EytseLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            EytseConnectionSwitch(coordinator),
            EytseSoundReactiveSwitch(coordinator),
            EytseInvertAxisSwitch(coordinator, "invert_x", "Invert X", "mdi:axis-x-arrow"),
            EytseInvertAxisSwitch(coordinator, "invert_y", "Invert Y", "mdi:axis-y-arrow"),
        ]
    )


class EytseConnectionSwitch(EytseLaserEntity, SwitchEntity):
    """Hold or release the single BLE connection.

    On = Home Assistant connects and polls the laser. Off = release the radio so
    another BLE controller can take the laser's single BLE connection slot.
    """

    _attr_name = "BLE connection"
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "connection")

    @property
    def available(self) -> bool:
        """The connection switch must always be usable, even when released."""
        return True

    @property
    def icon(self) -> str:
        """Icon reflects whether HA holds the radio."""
        return "mdi:bluetooth-connect" if self.coordinator.connection_enabled else "mdi:bluetooth-off"

    @property
    def is_on(self) -> bool:
        """Return whether HA is set to hold the BLE connection."""
        return self.coordinator.connection_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Connect and start polling."""
        await self.coordinator.async_set_connection(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Release the radio for another BLE controller."""
        await self.coordinator.async_set_connection(False)


class EytseSoundReactiveSwitch(EytseLaserEntity, SwitchEntity):
    """Make firmware effects react to the projector's onboard microphone.

    On = the playing firmware effect (animation/line/christmas/outdoor) reacts to
    room sound instead of running at a fixed speed; the sensitivity number sets
    the mic gain. The setting persists across restarts and is applied the next
    time an animation plays (or live, if one is already playing).
    """

    _attr_name = "Sound reactive"

    def __init__(self, coordinator) -> None:
        """Initialize the sound-reactive switch."""
        super().__init__(coordinator, "sound_reactive")

    @property
    def available(self) -> bool:
        """Editable even when the radio is released (applied on next play)."""
        return True

    @property
    def icon(self) -> str:
        """Icon reflects whether sound-reactive mode is enabled."""
        return "mdi:music-note" if self.coordinator.sound_reactive else "mdi:music-note-off"

    @property
    def is_on(self) -> bool:
        """Return whether sound-reactive playback is enabled."""
        return self.coordinator.sound_reactive

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable sound-reactive playback."""
        await self.coordinator.async_set_sound_reactive(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable sound-reactive playback."""
        await self.coordinator.async_set_sound_reactive(False)


class EytseInvertAxisSwitch(EytseLaserEntity, SwitchEntity):
    """Quick toggles for the projector-global mount inversion settings."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str, name: str, icon: str) -> None:
        """Initialize an axis-inversion switch."""
        super().__init__(coordinator, key)
        self._axis_key = key
        self._attr_name = name
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        """Return whether this axis is inverted by the current mount setting."""
        if self._axis_key == "invert_x":
            return self.coordinator.invert_x
        return self.coordinator.invert_y

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable inversion for this axis."""
        if self._axis_key == "invert_x":
            await self.coordinator.async_set_invert_x(True)
        else:
            await self.coordinator.async_set_invert_y(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable inversion for this axis."""
        if self._axis_key == "invert_x":
            await self.coordinator.async_set_invert_x(False)
        else:
            await self.coordinator.async_set_invert_y(False)
