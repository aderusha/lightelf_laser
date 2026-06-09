"""Base entity for the LightElf Laser integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN, MANUFACTURER
from .coordinator import LightElfLaserDataUpdateCoordinator


class LightElfLaserEntity(CoordinatorEntity[LightElfLaserDataUpdateCoordinator], Entity):
    """Base class for LightElf Laser entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LightElfLaserDataUpdateCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}-{key}"
        connections = set()
        if coordinator.bt_mac:
            connections.add((CONNECTION_BLUETOOTH, coordinator.bt_mac))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            connections=connections,
            name=coordinator.config_entry.data.get("name", DEFAULT_NAME),
            manufacturer=MANUFACTURER,
            model=coordinator.hardware_class,
            sw_version=coordinator.firmware_version,
        )

    @property
    def available(self) -> bool:
        """Available only when HA holds a usable BLE connection."""
        data = self.coordinator.data or {}
        return bool(data.get("connected")) and bool(data.get("can_send"))
