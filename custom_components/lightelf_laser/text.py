"""Text entity for the LightElf Laser integration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EytseLaserConfigEntry
from .entity import EytseLaserEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EytseLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the text-message entity."""
    async_add_entities([EytseTextMessage(config_entry.runtime_data)])


class EytseTextMessage(EytseLaserEntity, TextEntity):
    """The message that the Show Text button will draw."""

    _attr_name = "Text"
    _attr_icon = "mdi:format-text"
    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 100

    def __init__(self, coordinator) -> None:
        """Initialize the text entity."""
        super().__init__(coordinator, "text_message")

    @property
    def available(self) -> bool:
        """Editable even when the radio is released."""
        return True

    @property
    def native_value(self) -> str:
        """Return the current message."""
        return self.coordinator.text_message

    async def async_set_value(self, value: str) -> None:
        """Store the message for the next draw."""
        self.coordinator.text_message = value
        self.coordinator.async_update_listeners()
