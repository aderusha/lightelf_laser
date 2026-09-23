"""Capability diagnostic binary sensors for the LightElf Laser integration.

Each sensor reports whether the connected projector supports one firmware
capability, inferred from its reported hardware type and protocol version. These flags do
not imply integration support or successful testing on that model. They are all
diagnostic and disabled by default - turn on the ones you care about to see what
this specific box can do. ``Unknown`` until the first successful query.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    LightElfLaserConfigEntry,
    LightElfLaserDataUpdateCoordinator,
)
from .entity import LightElfLaserEntity
from .protocol import DeviceFeatures


@dataclass(frozen=True, kw_only=True)
class LightElfCapabilityDescription(BinarySensorEntityDescription):
    """Describes one capability flag and how to read it from DeviceFeatures."""

    feature_fn: Callable[[DeviceFeatures], bool]


CAPABILITIES: tuple[LightElfCapabilityDescription, ...] = (
    LightElfCapabilityDescription(
        key="cap_custom_animation",
        name="Firmware custom animation support",
        icon="mdi:movie-open-play",
        feature_fn=lambda f: f.pics_play,
    ),
    LightElfCapabilityDescription(
        key="cap_new_command_type",
        name="New command protocol",
        icon="mdi:protocol",
        feature_fn=lambda f: f.cmd_new_type,
    ),
    LightElfCapabilityDescription(
        key="cap_arbitrary_playback",
        name="Arbitrary playback",
        icon="mdi:playlist-play",
        feature_fn=lambda f: f.arb_play,
    ),
    LightElfCapabilityDescription(
        key="cap_new_projects",
        name="Extra project modes",
        icon="mdi:shape-plus",
        feature_fn=lambda f: f.new_projects,
    ),
    LightElfCapabilityDescription(
        key="cap_vertical_text",
        name="Vertical text scroll",
        icon="mdi:format-vertical-align-center",
        feature_fn=lambda f: f.text_up_down,
    ),
    LightElfCapabilityDescription(
        key="cap_xy_config",
        name="XY geometry config",
        icon="mdi:axis-arrow",
        feature_fn=lambda f: f.xy_cnf,
    ),
    LightElfCapabilityDescription(
        key="cap_ttl_animation",
        name="TTL animation",
        icon="mdi:animation",
        feature_fn=lambda f: f.ttl_animation,
    ),
    LightElfCapabilityDescription(
        key="cap_text_stop_markers",
        name="Text stop markers",
        icon="mdi:vector-point",
        feature_fn=lambda f: f.text_stop_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LightElfLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the capability diagnostic binary sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        LightElfCapabilitySensor(coordinator, description)
        for description in CAPABILITIES
    )


class LightElfCapabilitySensor(LightElfLaserEntity, BinarySensorEntity):
    """Reports whether the projector supports one firmware capability."""

    entity_description: LightElfCapabilityDescription
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: LightElfLaserDataUpdateCoordinator,
        description: LightElfCapabilityDescription,
    ) -> None:
        """Initialize the capability sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Available once identity is known; sticky across disconnects."""
        return self.coordinator.device_features is not None

    @property
    def is_on(self) -> bool | None:
        """Whether the capability is supported, or None until identity is read."""
        features = self.coordinator.device_features
        if features is None:
            return None
        return self.entity_description.feature_fn(features)
