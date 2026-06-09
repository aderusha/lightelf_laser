"""Diagnostic sensors for the LightElf Laser integration.

Four identity sensors are enabled by default (Bluetooth address, firmware
version, manufacturer, model). The lower-level values the projector reports -
hardware type, protocol/OTA version, device/user numbers, and the BLE streaming
budget - are added as default-disabled diagnostics for those who want them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MANUFACTURER
from .coordinator import (
    LightElfLaserConfigEntry,
    LightElfLaserDataUpdateCoordinator,
)
from .entity import LightElfLaserEntity


@dataclass(frozen=True, kw_only=True)
class LightElfSensorDescription(SensorEntityDescription):
    """Describes a LightElf diagnostic sensor and how to read its value."""

    value_fn: Callable[[LightElfLaserDataUpdateCoordinator], str | int | None]


def _ota_hex(coordinator: LightElfLaserDataUpdateCoordinator) -> str | None:
    if coordinator.ota_version is None:
        return None
    return f"{coordinator.ota_version:#06x}"


def _mtu(coordinator: LightElfLaserDataUpdateCoordinator) -> int | None:
    features = coordinator.device_features
    return features.ble_mtu if features else None


def _write_delay(coordinator: LightElfLaserDataUpdateCoordinator) -> int | None:
    features = coordinator.device_features
    return features.write_delay_ms if features else None


SENSORS: tuple[LightElfSensorDescription, ...] = (
    # -- enabled by default: human-facing identity --------------------------
    LightElfSensorDescription(
        key="bt_mac",
        name="Bluetooth address",
        icon="mdi:bluetooth",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.bt_mac or None,
    ),
    LightElfSensorDescription(
        key="firmware_version",
        name="Firmware version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.firmware_version,
    ),
    LightElfSensorDescription(
        key="manufacturer",
        name="Manufacturer",
        icon="mdi:factory",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: MANUFACTURER,
    ),
    LightElfSensorDescription(
        # The device reports no retail model, so "Model" carries the honest
        # device-reported hardware class (e.g. "Type 0 · v2"), not a SKU.
        key="model",
        name="Model",
        icon="mdi:format-list-bulleted-type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: c.hardware_class,
    ),
    # -- default-disabled: raw values the device reports --------------------
    LightElfSensorDescription(
        key="device_type",
        name="Hardware type",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.device_type,
    ),
    LightElfSensorDescription(
        key="protocol_version",
        name="Protocol version",
        icon="mdi:protocol",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.protocol_version,
    ),
    LightElfSensorDescription(
        key="ota_version",
        name="OTA version",
        icon="mdi:package-up",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_ota_hex,
    ),
    LightElfSensorDescription(
        key="device_number",
        name="Device number",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.device_number,
    ),
    LightElfSensorDescription(
        key="user_number",
        name="User number",
        icon="mdi:numeric",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: c.user_number,
    ),
    LightElfSensorDescription(
        key="ble_chunk_size",
        name="BLE chunk size",
        icon="mdi:transfer",
        native_unit_of_measurement="B",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_mtu,
    ),
    LightElfSensorDescription(
        key="ble_write_delay",
        name="BLE write delay",
        icon="mdi:timer-sand",
        native_unit_of_measurement="ms",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_write_delay,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LightElfLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the diagnostic sensors."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        LightElfDiagnosticSensor(coordinator, description) for description in SENSORS
    )


class LightElfDiagnosticSensor(LightElfLaserEntity, SensorEntity):
    """A read-only diagnostic value derived from the projector's identity."""

    entity_description: LightElfSensorDescription

    def __init__(
        self,
        coordinator: LightElfLaserDataUpdateCoordinator,
        description: LightElfSensorDescription,
    ) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Diagnostics stay available, showing the last-known identity.

        Identity is latched from the first query and kept across disconnects, so
        these should not flicker to Unavailable when the radio is released.
        """
        return True

    @property
    def native_value(self) -> str | int | None:
        """Return the current diagnostic value."""
        return self.entity_description.value_fn(self.coordinator)
