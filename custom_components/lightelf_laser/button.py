"""Button entities for the LightElf Laser integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LightElfLaserConfigEntry, LightElfLaserDataUpdateCoordinator
from .entity import LightElfLaserEntity


@dataclass(frozen=True, kw_only=True)
class LightElfButtonDescription(ButtonEntityDescription):
    """Button metadata."""

    action: Callable[[LightElfLaserDataUpdateCoordinator], Awaitable[None]]
    # When True the button needs a live BLE connection; when False it works
    # regardless (e.g. a filesystem rescan).
    needs_connection: bool = True


BUTTONS = (
    LightElfButtonDescription(
        key="display_svg",
        name="Show SVG",
        icon="mdi:projector",
        action=lambda coordinator: coordinator.async_display_svg(),
    ),
    LightElfButtonDescription(
        key="display_text",
        name="Show Text",
        icon="mdi:format-text",
        action=lambda coordinator: coordinator.async_display_text(),
    ),
    LightElfButtonDescription(
        key="display_shape",
        name="Show Shape",
        icon="mdi:shape-plus",
        action=lambda coordinator: coordinator.async_display_shape(),
    ),
    LightElfButtonDescription(
        key="play_animation",
        name="Show Animation",
        icon="mdi:play-box",
        action=lambda coordinator: coordinator.async_display_native_animation(),
    ),
    LightElfButtonDescription(
        key="rescan_svg",
        name="Rescan SVG folder",
        icon="mdi:folder-refresh",
        entity_category=EntityCategory.CONFIG,
        needs_connection=False,
        action=lambda coordinator: coordinator.async_rescan_svgs(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LightElfLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up button entities."""
    coordinator = config_entry.runtime_data
    async_add_entities(LightElfButton(coordinator, description) for description in BUTTONS)


class LightElfButton(LightElfLaserEntity, ButtonEntity):
    """A laser action button."""

    def __init__(self, coordinator, description: LightElfButtonDescription) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name

    @property
    def available(self) -> bool:
        """Connection-free buttons stay usable; others need a live link."""
        if not self.entity_description.needs_connection:
            return True
        return super().available

    async def async_press(self) -> None:
        """Press the button."""
        await self.entity_description.action(self.coordinator)
