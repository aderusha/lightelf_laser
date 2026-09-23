"""Downloadable, content-free diagnostics for LightElf Laser."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .protocol import resolve_device_features

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from .coordinator import LightElfLaserConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LightElfLaserConfigEntry
) -> dict[str, Any]:
    """Export cached, allowlisted metadata without taking the BLE connection.

    Never include entry data/options, arbitrary exception messages, raw packets,
    text, file paths, Bluetooth addresses, names, passwords, or challenge tokens.
    A successful write means delivery to the Bluetooth stack, not confirmation
    that the projector displayed the requested content.
    """
    integration = await async_get_integration(hass, DOMAIN)
    coordinator = getattr(entry, "runtime_data", None)
    result: dict[str, Any] = {
        "schema_version": 2,
        "integration_version": integration.version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "loaded": coordinator is not None,
    }
    if coordinator is None:
        return result

    transport = coordinator.client.diagnostic_snapshot()
    identity = transport["last_query"]
    features = (
        resolve_device_features(identity["device_type"], identity["protocol_version"])
        if identity else None
    )
    result.update({
        "connection_enabled": coordinator.connection_enabled,
        "last_update_success": coordinator.last_update_success,
        "transport": transport,
        "inferred_firmware_capabilities": asdict(features) if features else None,
        "integration_behavior": {
            "drawing_format": "legacy",
            "scrolling_text_format": "legacy",
            "animation_catalog": "reference_device",
            "new_format_drawing_implemented": False,
        },
        "compatibility": {
            "new_format_device_using_legacy_draw": bool(features and features.cmd_new_type),
            "hardware_validation": (
                "reference_type_0_version_2" if features and
                (features.device_type, features.version) == (0, 2)
                else "unverified" if features else "identity_unknown"
            ),
        },
        "compatibility_scan": getattr(coordinator, "discovery_report", None),
        "compatibility_scan_status": getattr(coordinator, "discovery_status", "idle"),
    })
    return result
