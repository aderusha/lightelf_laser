"""Offline regression checks using a simulated Bluetooth transport.

Run with: python -m unittest discover -s tests -v
These tests do not start Home Assistant or access Bluetooth hardware.
"""

import asyncio
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "lightelf_offline_tests"


class Generic:
    @classmethod
    def __class_getitem__(cls, item):
        return cls


def load_modules():
    """Load production modules with only framework boundaries substituted."""
    package = ModuleType(PACKAGE)
    package.__path__ = [str(ROOT / "custom_components/lightelf_laser")]
    sys.modules[PACKAGE] = package
    modules = {}
    definitions = {
        "homeassistant": {},
        "homeassistant.components": {},
        "homeassistant.components.bluetooth": {},
        "homeassistant.const": {
            "CONF_ADDRESS": "address",
            "Platform": SimpleNamespace(**{
                name: name.lower() for name in (
                    "LIGHT", "SWITCH", "SELECT", "NUMBER", "TEXT", "IMAGE",
                    "BUTTON", "SENSOR", "BINARY_SENSOR",
                )
            }),
        },
        "homeassistant.core": {"HomeAssistant": Generic},
        "homeassistant.config_entries": {"ConfigEntry": Generic},
        "homeassistant.helpers": {},
        "homeassistant.helpers.update_coordinator": {"DataUpdateCoordinator": Generic},
        "homeassistant.loader": {
            "async_get_integration": AsyncMock(return_value=SimpleNamespace(version="test"))
        },
        "bleak_retry_connector": {
            "BLEAK_RETRY_EXCEPTIONS": (OSError,),
            "BleakClientWithServiceCache": Generic,
            "close_stale_connections": AsyncMock(),
            "establish_connection": AsyncMock(),
        },
    }
    for name, values in definitions.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        modules[name] = module
    with patch.dict(sys.modules, modules):
        return tuple(importlib.import_module(f"{PACKAGE}.{name}") for name in (
            "protocol", "bluetooth_client", "diagnostics", "coordinator"
        ))


protocol, bluetooth, diagnostics, coordinator_module = load_modules()


def make_client():
    client = bluetooth.LightElfBluetoothClient(SimpleNamespace(), "AA:BB:CC:DD:EE:FF")
    client._client = SimpleNamespace(is_connected=True, write_gatt_char=AsyncMock())
    client._profile = protocol.UUID_PROFILES["ff00"]
    return client


def make_reply(device_type=0, version=2):
    raw = (
        "E0E1E2E303000400" + protocol.settings_command(password=1234)
        + protocol.mode_command(mode=3) + "43E3A317FF"
        + f"{device_type:02X}{version:02X}01E4E5E6E7"
    )
    return protocol.parse_query_reply(raw, [100, 50, 200, 0])


class FeatureTests(unittest.TestCase):
    def test_generation_boundaries(self):
        for kind, version, new, count64 in (
            (0, 2, False, False), (0, 30, False, False),
            (0, 47, False, False), (0, 48, True, False),
            (0, 49, True, True), (1, 1, False, False),
            (2, 2, False, False), (3, 2, True, False), (4, 2, True, True),
        ):
            with self.subTest(kind=kind, version=version):
                features = protocol.resolve_device_features(kind, version)
                self.assertEqual(features.cmd_new_type, new)
                self.assertEqual(features.project_items_64, count64)

    def test_reference_packets_unchanged(self):
        self.assertEqual(protocol.power_command(False, cmd_new_type=False),
                         "B0B1B2B300B4B5B6B7")
        self.assertEqual(protocol.query_command([0x12, 0x34, 0x56, 0x78]),
                         "E0E1E2E312345678E4E5E6E7")


class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_omits_private_content_and_does_not_connect(self):
        client = make_client()
        client._remember_query_state(make_reply(3, 2))
        client._ensure_connected_locked = AsyncMock(side_effect=AssertionError("must not connect"))
        coordinator = SimpleNamespace(
            client=client, connection_enabled=False, last_update_success=True,
            text_message="PRIVATE MESSAGE", selected_svg="private-file.svg",
        )
        entry = SimpleNamespace(runtime_data=coordinator,
                                data={"address": client.address, "name": "Private room"},
                                options={"password": "secret"})
        result = await diagnostics.async_get_config_entry_diagnostics(None, entry)
        encoded = json.dumps(result)
        for private in (client.address, "Private room", "PRIVATE MESSAGE", "private-file.svg",
                        "secret", "43E3A317", "raw_hex", "password"):
            self.assertNotIn(private, encoded)
        self.assertTrue(result["compatibility"]["new_format_device_using_legacy_draw"])
        self.assertFalse(result["connection_enabled"])
        self.assertEqual(result["transport"]["last_query"]["device_type"], 3)
        self.assertEqual(result["transport"]["last_reported_mode"]["mode"], 3)
        client._ensure_connected_locked.assert_not_awaited()

    async def test_unknown_identity_is_not_reported_as_legacy_hardware(self):
        entry = SimpleNamespace(runtime_data=SimpleNamespace(
            client=make_client(), connection_enabled=True, last_update_success=False,
        ))
        result = await diagnostics.async_get_config_entry_diagnostics(None, entry)
        self.assertIsNone(result["inferred_firmware_capabilities"])
        self.assertEqual(result["compatibility"]["hardware_validation"], "identity_unknown")

    async def test_unloaded_entry(self):
        result = await diagnostics.async_get_config_entry_diagnostics(None, SimpleNamespace())
        self.assertFalse(result["loaded"])

    async def test_snapshot_is_detached(self):
        client = make_client()
        client._remember_query_state(make_reply())
        snapshot = client.diagnostic_snapshot()
        snapshot["last_query"]["device_type"] = 99
        self.assertEqual(client.diagnostic_snapshot()["last_query"]["device_type"], 0)

    async def test_actual_write_timing_and_content_free_history(self):
        client = make_client()
        script = protocol.draw_points_command([[0, 0, 0, 2], [100, 100, 5, 3]])
        with patch.object(bluetooth.asyncio, "sleep", new_callable=AsyncMock) as sleep:
            await client._write_script_locked(script)
        calls = client._client.write_gatt_char.call_args_list
        self.assertTrue(all(len(call.args[1]) <= 20 for call in calls))
        self.assertTrue(all(call.kwargs["response"] is False for call in calls))
        self.assertTrue(all(call.args == (0.03,) for call in sleep.call_args_list))
        event = client.diagnostic_snapshot()["recent_operations"][-1]
        self.assertEqual(event["result"], "written")
        self.assertEqual(event["operation"], "draw")
        self.assertEqual(event["bytes"], len(script) // 2)
        self.assertNotIn(script, json.dumps(event))

    async def test_write_failure_keeps_type_not_exception_text(self):
        client = make_client()
        client._client.write_gatt_char.side_effect = OSError("AA:BB:CC:DD:EE:FF private-file.svg")
        with self.assertRaises(OSError):
            await client._write_script_locked(protocol.power_command(False))
        event = client.diagnostic_snapshot()["recent_operations"][-1]
        self.assertEqual(event["error_type"], "OSError")
        self.assertEqual(event["result"], "failed")
        self.assertNotIn("private-file", json.dumps(event))
        self.assertNotIn(client.address, json.dumps(event))

    async def test_history_is_bounded(self):
        client = make_client()
        with patch.object(bluetooth.asyncio, "sleep", new_callable=AsyncMock):
            for _ in range(40):
                await client._write_script_locked(protocol.power_command(False))
        self.assertEqual(len(client.diagnostic_snapshot()["recent_operations"]), 32)

    async def test_settings_use_detected_generation(self):
        for kind, version, expected_new in ((1, 1, False), (3, 2, True), (0, 48, True)):
            client = make_client()
            client._remember_query_state(make_reply(kind, version))
            client._ensure_connected_locked = AsyncMock()
            client._write_script_locked = AsyncMock()
            with patch.object(bluetooth, "settings_command", wraps=protocol.settings_command) as build:
                await client._send_settings({"dmx_address": 25})
            self.assertEqual(build.call_args.kwargs["cmd_new_type"], expected_new)
            self.assertEqual(build.call_args.kwargs["password"], 1234)

    async def test_bad_challenge_does_not_replace_identity(self):
        client = make_client()
        client._remember_query_state(make_reply())
        old_identity = client.diagnostic_snapshot()["last_query"]

        async def reply_to_query(command):
            client._reply_chunks.append(bytes.fromhex(
                make_reply(3, 2).raw_hex.replace("43E3A317", "00000000")
            ))
            client._reply_event.set()

        client._write_script_locked = reply_to_query
        with patch.object(bluetooth.random, "randrange", side_effect=[100, 50, 200, 0]):
            with self.assertRaises(bluetooth.LightElfBluetoothError):
                await client._query_locked()
        snapshot = client.diagnostic_snapshot()
        self.assertEqual(snapshot["last_query"], old_identity)
        self.assertEqual(snapshot["recent_operations"][-1]["result"], "failed")
        self.assertIsNone(client._reply_chunks)

    async def test_cancelled_write_is_visible(self):
        client = make_client()
        client._client.write_gatt_char.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await client._write_script_locked(protocol.power_command(False))
        self.assertEqual(client.diagnostic_snapshot()["recent_operations"][-1]["result"],
                         "cancelled")

    async def test_panel_mode_readback_updates_active_show(self):
        cls = coordinator_module.LightElfLaserDataUpdateCoordinator
        coordinator = object.__new__(cls)
        coordinator.hass = SimpleNamespace(async_add_executor_job=AsyncMock(return_value=[]))
        coordinator.selected_svg = None
        coordinator.connection_enabled = True
        coordinator.is_on = True
        coordinator._active_show_program = 5
        coordinator._native_animation_active = True
        coordinator.mount_xy = 1
        coordinator.dmx_address = 1
        coordinator.client = SimpleNamespace(request=AsyncMock(return_value={
            "data": {"device_on": True, "mode_state": {"mode": 2}},
        }))
        await coordinator._async_update_data()
        self.assertEqual(coordinator._active_show_program, 2)

    async def test_invalid_show_does_not_write(self):
        cls = coordinator_module.LightElfLaserDataUpdateCoordinator
        coordinator = object.__new__(cls)
        coordinator.client = SimpleNamespace(request=AsyncMock())
        with self.assertRaises(coordinator_module.LightElfLaserError):
            await coordinator.async_set_show_program(9)
        coordinator.client.request.assert_not_awaited()

    async def test_sound_adjustment_preserves_show_program(self):
        cls = coordinator_module.LightElfLaserDataUpdateCoordinator
        coordinator = object.__new__(cls)
        coordinator.is_on = True
        coordinator.connection_enabled = True
        coordinator._native_animation_active = True
        coordinator._active_show_program = 5
        coordinator.async_set_show_program = AsyncMock()
        coordinator.async_display_native_animation = AsyncMock()
        await coordinator._reapply_sound_if_playing()
        coordinator.async_set_show_program.assert_awaited_once_with(5)
        coordinator.async_display_native_animation.assert_not_awaited()

    async def test_animation_sound_adjustment_still_replays_animation(self):
        cls = coordinator_module.LightElfLaserDataUpdateCoordinator
        coordinator = object.__new__(cls)
        coordinator.is_on = True
        coordinator.connection_enabled = True
        coordinator._native_animation_active = True
        coordinator._active_show_program = None
        coordinator.async_display_native_animation = AsyncMock()
        await coordinator._reapply_sound_if_playing()
        coordinator.async_display_native_animation.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
