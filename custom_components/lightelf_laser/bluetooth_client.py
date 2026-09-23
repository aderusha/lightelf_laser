"""Native Home Assistant Bluetooth transport for LightElf Laser."""

from __future__ import annotations

import asyncio
import random
from collections import deque
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    close_stale_connections,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .const import LOGGER
from .errors import LightElfLaserError
from .protocol import (
    PROJECT_SELECTED,
    UUID_PROFILES,
    ProjectSelection,
    SettingsState,
    clean_hex,
    draw_text_command,
    mode_command,
    ModeState,
    parse_device_state,
    parse_query_reply,
    point_play_command,
    power_command,
    query_command,
    reply_complete,
    resolve_device_features,
    send_script_to_chunks,
    settings_command,
)


class LightElfBluetoothError(LightElfLaserError):
    """Raised when native Bluetooth cannot reach or command the laser."""


_RETRY_EXCEPTIONS = (*BLEAK_RETRY_EXCEPTIONS, LightElfBluetoothError)
WRITE_CHUNK_SIZE = 20
WRITE_DELAY_SECONDS = 0.03
_COMMAND_NAMES = {
    "E0E1E2E3": "query", "B0B1B2B3": "power", "C0C1C2C3": "mode",
    "00010203": "settings", "F0F1F2F3": "draw", "A0A1A2A3": "text",
    "70717073": "point_play", "D0D1D2D3": "effect",
    "F0F1F200": "draw_new",
}

NATIVE_BUILTIN_FAMILIES = {
    "line": {"mode": 2, "project": 2, "max": 50},
    "animation": {"mode": 3, "project": 3, "max": 50},
    "animationa": {"mode": 3, "project": 3, "max": 50},
    "christmas": {"mode": 5, "project": 5, "max": 50},
    "outdoor": {"mode": 6, "project": 6, "max": 50},
}

_MODE_ARG_ALIASES = {
    "size": "size_percent",
    "speed": "speed_percent",
    "distance": "distance_percent",
    "sound": "sound_percent",
}

_MODE_KWARGS = {
    "color",
    "size_percent",
    "speed_percent",
    "distance_percent",
    "playback",
    "sound_percent",
    "run_direction",
    "text_point_time",
    "group_colors",
    "projects",
    "arb_play",
    "new_prjs",
    "cmd_new_type",
    "text_stop_time",
}


def _mode_kwargs_from_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in args.items():
        mapped = _MODE_ARG_ALIASES.get(key, key)
        if mapped in _MODE_KWARGS:
            out[mapped] = value
    return out


def _pattern_tuple(args: dict[str, Any], max_pattern: int) -> tuple[int, ...]:
    raw = args.get("patterns", args.get("pattern", args.get("index", 1)))
    if isinstance(raw, str):
        patterns = tuple(int(item.strip()) for item in raw.split(",") if item.strip())
    elif isinstance(raw, (list, tuple)):
        patterns = tuple(int(item) for item in raw)
    else:
        patterns = (int(raw),)
    bad = [item for item in patterns if item < 1 or item > max_pattern or item > 64]
    if bad:
        raise LightElfBluetoothError(
            f"pattern(s) out of range 1..{min(max_pattern, 64)}: {bad}"
        )
    return patterns


def _native_builtin_commands(args: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    family = str(args.get("family", "animation")).lower().replace(" ", "")
    if family not in NATIVE_BUILTIN_FAMILIES:
        known = ", ".join(sorted(NATIVE_BUILTIN_FAMILIES))
        raise LightElfBluetoothError(f"unknown native family {family!r}; known: {known}")
    info = NATIVE_BUILTIN_FAMILIES[family]
    patterns = _pattern_tuple(args, int(info["max"]))
    preview = args.get("preview_pattern", args.get("preview", patterns[0]))
    project = int(info["project"])
    mode_num = int(args.get("mode", info["mode"]))
    kwargs = _mode_kwargs_from_args(args)
    kwargs.pop("projects", None)
    kwargs.setdefault("color", args.get("color", 9))
    kwargs.setdefault("size_percent", int(args.get("size_percent", args.get("size", 50))))
    kwargs.setdefault("speed_percent", int(args.get("speed_percent", args.get("speed", 70))))
    kwargs.setdefault(
        "distance_percent", int(args.get("distance_percent", args.get("distance", 50)))
    )
    kwargs.setdefault("playback", args.get("playback", "auto"))
    kwargs.setdefault("sound_percent", int(args.get("sound_percent", args.get("sound", 50))))
    kwargs["projects"] = {
        project: ProjectSelection(
            py_mode=PROJECT_SELECTED,
            selected_patterns=patterns,
            preview_pattern=None if preview in (None, "") else int(preview),
        )
    }
    return (
        [point_play_command(""), mode_command(mode=mode_num, **kwargs)],
        {
            "family": family,
            "mode": mode_num,
            "project": project,
            "patterns": patterns,
        },
    )


class LightElfBluetoothClient:
    """HA-native BLE client with a persistent notify/unlock session."""

    def __init__(self, hass: HomeAssistant, address: str, timeout: float = 10.0) -> None:
        """Initialize the native Bluetooth client."""
        self.hass = hass
        self.address = address.upper()
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._profile: dict[str, str] | None = None
        self._notify_started: list[str] = []
        self._can_send = False
        self._reply_chunks: list[bytes] | None = None
        self._reply_event: asyncio.Event | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._device_on = False
        self._device_type = 0
        self._features = None
        self._last_query: dict[str, Any] | None = None
        self._history: deque[dict[str, Any]] = deque(maxlen=32)
        self._write_properties: list[str] = []
        self._last_profile: dict[str, str] | None = None
        self._gatt_services: list[dict[str, Any]] = []
        self._last_rssi_dbm: int | None = None
        self._last_connect_ms: int | None = None
        self._settings_state: SettingsState | None = None
        self._mode_state: ModeState | None = None
        # Pace unacknowledged writes for reliable delivery through proxies.
        self._write_response = False
        self.discovery_active = False

    @property
    def write_chunk_size(self) -> int:
        return WRITE_CHUNK_SIZE

    @property
    def write_delay_ms(self) -> int:
        return 1 if self._write_response else round(WRITE_DELAY_SECONDS * 1000)

    def diagnostic_snapshot(self) -> dict[str, Any]:
        """Return cached metadata only; never connect or expose payload content."""
        return deepcopy({
            "connected": bool(self._client and self._client.is_connected),
            "can_send": self._can_send,
            "profile": self._last_profile,
            "gatt_services": self._gatt_services,
            "negotiated_mtu": self._safe_mtu(),
            "last_rssi_dbm": self._last_rssi_dbm,
            "last_connect_ms": self._last_connect_ms,
            "write_properties": self._write_properties,
            "write_with_response": self._write_response,
            "write_chunk_size": self.write_chunk_size,
            "write_delay_ms": self.write_delay_ms,
            "last_query": self._last_query,
            "last_reported_mode": self._mode_state_data(),
            "recent_operations": list(self._history),
        })

    def _safe_mtu(self) -> int | None:
        try:
            value = getattr(self._client, "mtu_size", None)
            return int(value) if value is not None else None
        except Exception:
            return None

    async def async_probe_packets(
        self,
        packets: list[tuple[str, str]],
        *,
        first_delay: float = 0.35,
        second_delay: float = 1.25,
    ) -> dict[str, Any]:
        """Send fixed discovery packets and retain both early and late read-backs.

        The caller supplies only integration-owned test packets. The BLE lock
        keeps normal traffic out of each packet/read-back sequence. Returned
        metadata contains no packet contents or exception messages.
        """
        result: dict[str, Any] = {"writes": [], "readbacks": []}
        async with self._lock:
            try:
                await self._ensure_connected_locked()
            except Exception as err:
                result["error_type"] = type(err).__name__
                result["error_phase"] = "connect"
                return result
            for label, packet in packets:
                try:
                    await self._write_script_locked(packet)
                except Exception as err:
                    result["error_type"] = type(err).__name__
                    result["error_phase"] = label
                result["writes"].append({
                    "label": label,
                    **deepcopy(self._history[-1]),
                })
                if "error_type" in result:
                    return result
            for label, delay in (("early", first_delay), ("settled", second_delay)):
                await asyncio.sleep(delay)
                try:
                    await self._query_locked()
                    result["readbacks"].append({
                        "phase": label,
                        "result": "ok",
                        **deepcopy(self._last_query or {}),
                        "mode_state": self._mode_state_data(),
                    })
                except Exception as err:
                    result["readbacks"].append({
                        "phase": label,
                        "result": "failed",
                        "error_type": type(err).__name__,
                    })
            return result

    @property
    def device_id(self) -> str:
        """Return a stable device identifier."""
        return f"ble:{self.address}"

    def _ble_device(self) -> Any:
        return bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )

    def _profile_for_client(self, client: BleakClientWithServiceCache) -> dict[str, str]:
        services_obj = client.services
        try:
            service_iter = list(services_obj)
        except TypeError:
            service_iter = list(getattr(services_obj, "services", {}).values())
        available = {str(service.uuid).upper(): service for service in service_iter}
        self._gatt_services = []
        for service in service_iter[:32]:
            item: dict[str, Any] = {"uuid": str(service.uuid).upper(), "characteristics": []}
            try:
                characteristics = getattr(service, "characteristics", []) or []
                if isinstance(characteristics, dict):
                    characteristics = characteristics.values()
                item["characteristics"] = [
                    {
                        "uuid": str(char.uuid).upper(),
                        "properties": sorted(str(prop) for prop in (getattr(char, "properties", []) or [])),
                    }
                    for char in list(characteristics)[:32]
                ]
            except Exception:
                # GATT inventory is diagnostic only; it must never prevent a
                # connection to an otherwise usable profile.
                pass
            self._gatt_services.append(item)
        for profile in UUID_PROFILES.values():
            if profile["service"].upper() in available:
                return profile
        seen = ", ".join(sorted(available))
        raise LightElfBluetoothError(f"No known LightElf service found. Available: {seen}")

    def _resolve_write_mode(self) -> None:
        """Decide acked vs unacked writes from the write char's properties."""
        self._write_response = False
        if self._client is None or self._profile is None:
            return
        try:
            char = self._client.services.get_characteristic(self._profile["write"])
            props = list(getattr(char, "properties", []) or [])
        except Exception:
            props = []
        # This device's FF02 advertises both 'write' and 'write-without-response'.
        # Acked writes ('write') are reliable on direct BlueZ but, through the
        # ESPHome BT proxy, each blocks on a round-trip and the device finalizes
        # the draw frame early -> truncated text. So we deliberately use unacked
        # writes (fast enough that the whole frame lands inside the device's
        # frame-assembly window) and pace them to keep the proxy from reordering.
        self._write_response = False
        self._write_properties = [p for p in props if p in {
            "read", "write", "write-without-response", "notify", "indicate"
        }]
        self._last_profile = dict(self._profile)
        LOGGER.debug("LightElf write char properties=%s (using unacked writes)", props)

    async def _disconnect_locked(self) -> None:
        self._can_send = False
        self._profile = None
        self._notify_started = []
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    def _on_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        self._can_send = False
        self._profile = None
        self._notify_started = []
        self._client = None

    def _on_notify(self, _sender: int, data: bytearray) -> None:
        if self._reply_chunks is None or self._reply_event is None:
            return
        self._reply_chunks.append(bytes(data))
        current = b"".join(self._reply_chunks).hex().upper()
        if reply_complete(current):
            self._reply_event.set()

    async def _write_script_locked(self, script: str) -> None:
        if self._client is None or self._profile is None:
            raise LightElfBluetoothError("Bluetooth client is not connected")
        cleaned = clean_hex(script)
        chunks = send_script_to_chunks(script, chunk_size=self.write_chunk_size)
        event = {
            "time": datetime.now(timezone.utc).isoformat(),
            "operation": _COMMAND_NAMES.get(cleaned[:8], "other"),
            "bytes": sum(len(chunk) for chunk in chunks if isinstance(chunk, bytes)),
            "chunks_written": 0,
            "result": "cancelled",
        }
        started = monotonic()
        try:
            for chunk in chunks:
                if chunk == "split":
                    await asyncio.sleep(0.1)
                    continue
                if chunk == "reply":
                    raise LightElfBluetoothError("Reply marker is not supported in send scripts")
                await self._client.write_gatt_char(
                    self._profile["write"], chunk, response=self._write_response
                )
                event["chunks_written"] += 1
                await asyncio.sleep(self.write_delay_ms / 1000)
            event["result"] = "written"
        except Exception as err:
            event["result"] = "failed"
            event["error_type"] = type(err).__name__
            raise
        finally:
            event["duration_ms"] = round((monotonic() - started) * 1000)
            self._history.append(event)

    async def _query_locked(self) -> Any:
        started = monotonic()
        random_bytes = [random.randrange(256) for _ in range(4)]
        command = query_command(random_bytes)
        self._reply_chunks = []
        self._reply_event = asyncio.Event()
        try:
            for attempt in range(1, 4):
                await self._write_script_locked(command)
                try:
                    await asyncio.wait_for(self._reply_event.wait(), timeout=8.0)
                    break
                except TimeoutError:
                    if attempt == 3:
                        raise
                    self._reply_chunks.clear()
                    self._reply_event.clear()
            raw = b"".join(self._reply_chunks).hex().upper()
            parsed = parse_query_reply(raw, random_bytes)
            if not parsed.challenge_ok:
                raise LightElfBluetoothError("LightElf query challenge failed")
            self._remember_query_state(parsed)
            self._last_query["query_attempts"] = attempt
            self._last_query["query_duration_ms"] = round((monotonic() - started) * 1000)
            self._last_query["notify_chunks"] = len(self._reply_chunks)
            self._last_query["notify_chunk_lengths"] = [len(chunk) for chunk in self._reply_chunks]
            return parsed
        except Exception as err:
            self._history.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "operation": "query_reply", "result": "failed",
                "error_type": type(err).__name__,
                "duration_ms": round((monotonic() - started) * 1000),
                "notify_chunks": len(self._reply_chunks),
            })
            raise
        finally:
            self._reply_chunks = None
            self._reply_event = None

    def _remember_query_state(self, parsed: Any) -> None:
        """Cache query-derived state needed to preserve settings writes."""
        self._device_on = bool(parsed.device_on)
        self._device_type = int(parsed.device_type)
        self._features = resolve_device_features(parsed.device_type, parsed.version)
        self._last_query = {
            "time": datetime.now(timezone.utc).isoformat(),
            "reply_bytes": len(parsed.raw_hex) // 2,
            "challenge_ok": parsed.challenge_ok,
            "device_on": parsed.device_on,
            "device_type": parsed.device_type,
            "protocol_version": parsed.version,
            "device_number": parsed.device_number,
            "user_number": parsed.user_number,
            "ota_version_raw": parsed.ota_version,
            "reply_terminator": (
                "query_envelope" if parsed.raw_hex.endswith("E4E5E6E7") else "other"
            ),
            "frame_layout": self._query_frame_layout(parsed.raw_hex),
        }
        try:
            state = parse_device_state(
                parsed.raw_hex,
                query=parsed,
                cmd_new_type=self._features.cmd_new_type,
                xy_cnf=self._features.xy_cnf,
            )
        except Exception as err:
            self._last_query["state_parse_error_type"] = type(err).__name__
            LOGGER.debug("Could not parse full LightElf query state: %s", err)
            return
        self._last_query["parsed_blocks"] = {
            name: getattr(state, name) is not None
            for name in ("power", "mode", "settings", "xy_config", "pis", "draw")
        }
        if state.settings is not None:
            self._settings_state = state.settings
        if state.mode is not None:
            self._mode_state = state.mode
        # Allowlist the useful state fields. Raw blocks, passwords, and saved
        # user content stay out of diagnostics and discovery reports.
        self._last_query["readback"] = {
            "power_on": state.power.on if state.power is not None else None,
            "settings": ({
                "dmx_address": state.settings.dmx_address,
                "channel": state.settings.channel,
                "display_size": state.settings.display_size,
                "xy": state.settings.xy,
                "red": state.settings.red,
                "green": state.settings.green,
                "blue": state.settings.blue,
                "light": state.settings.light,
                "cfg": state.settings.cfg,
                "power": state.settings.power,
                "brightness": state.settings.brightness,
                "grating": state.settings.grating,
            } if state.settings is not None else None),
            "draw": ({
                "point_count": state.draw.point_count,
                "save_tag": state.draw.save_tag,
                "config_values": list(state.draw.config_values),
            } if state.draw is not None else None),
            "pis": ({
                "count": state.pis.count,
                "list_mode": state.pis.list_mode,
                "indices": [entry.index for entry in state.pis.entries],
            } if state.pis is not None else None),
            "xy_config": ({
                "save": state.xy_config.save,
                "phase": state.xy_config.phase,
                "x_big": state.xy_config.x_big,
                "x_small": state.xy_config.x_small,
                "y_big": state.xy_config.y_big,
                "y_small": state.xy_config.y_small,
            } if state.xy_config is not None else None),
        }

    @staticmethod
    def _query_frame_layout(raw_hex: str) -> list[dict[str, Any]]:
        """Describe known frame boundaries without exposing payload bytes."""
        markers = (
            ("power", "B0B1B2B3", "B4B5B6B7"),
            ("mode", "C0C1C2C3", "C4C5C6C7"),
            ("settings", "00010203", "04050607"),
            ("xy_config", "10111213", "14151617"),
            ("pis", "D0D1D2D3", "D4D5D6D7"),
            ("draw_legacy", "F0F1F2F3", "F4F5F6F7"),
            ("draw_new", "F0F1F200", "F6F7"),
        )
        layout = []
        for name, start, end in markers:
            position = raw_hex.find(start)
            if position < 0:
                continue
            finish = raw_hex.find(end, position + len(start))
            if finish < 0:
                continue
            layout.append({
                "name": name,
                "offset_bytes": position // 2,
                "payload_bytes": (finish - position - len(start)) // 2,
            })
        return sorted(layout, key=lambda item: item["offset_bytes"])

    def _mode_state_data(self) -> dict[str, Any] | None:
        state = self._mode_state
        if state is None:
            return None
        return {
            "mode": state.mode,
            "color": state.color,
            "speed_percent": state.speed_percent,
            "distance_percent": state.distance_percent,
            "playback": state.playback,
            "projects": {
                str(project_id): {
                    "py_mode": project.py_mode,
                    "preview_pattern": project.preview_pattern,
                    "selected_patterns": list(project.selected_patterns),
                    "selected_words": list(project.selected_words),
                }
                for project_id, project in state.projects.items()
            },
        }

    async def _start_notify_locked(self) -> None:
        if self._client is None or self._profile is None or self._notify_started:
            return
        notify_chars = [self._profile["notify"]]
        if self._profile["write"].upper() != self._profile["notify"].upper():
            notify_chars.append(self._profile["write"])
        for char_uuid in notify_chars:
            try:
                await self._client.start_notify(char_uuid, self._on_notify)
                self._notify_started.append(char_uuid)
            except Exception:
                if char_uuid == self._profile["notify"]:
                    raise
        await asyncio.sleep(0.2)

    async def _ensure_connected_locked(self) -> None:
        if self._client is not None and self._client.is_connected and self._can_send:
            return

        started = monotonic()
        await self._disconnect_locked()
        ble_device = self._ble_device()
        if ble_device is None:
            raise LightElfBluetoothError(
                f"{self.address} is not currently available through HA Bluetooth"
            )
        try:
            rssi = getattr(ble_device, "rssi", None)
            self._last_rssi_dbm = int(rssi) if rssi is not None else None
        except Exception:
            self._last_rssi_dbm = None

        await close_stale_connections(ble_device)
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            f"LightElf Laser {self.address}",
            self._on_disconnect,
            max_attempts=4,
            ble_device_callback=self._ble_device,
            timeout=self.timeout,
        )
        self._profile = self._profile_for_client(self._client)
        self._resolve_write_mode()
        await self._start_notify_locked()
        parsed = await self._query_locked()
        if not parsed.challenge_ok:
            raise LightElfBluetoothError(
                f"LightElf query challenge failed: token={parsed.challenge_token}"
            )
        self._can_send = True
        self._last_connect_ms = round((monotonic() - started) * 1000)

    async def _send_commands(self, commands: list[str]) -> None:
        last_error: BaseException | None = None
        for attempt in range(1, 3):
            async with self._lock:
                try:
                    await self._ensure_connected_locked()
                    for command in commands:
                        await self._write_script_locked(command)
                    return
                except _RETRY_EXCEPTIONS as err:
                    last_error = err
                    await self._disconnect_locked()
            if attempt < 2:
                await asyncio.sleep(1.0)
        raise LightElfBluetoothError(str(last_error) if last_error else "Bluetooth write failed")

    async def _query_state(self) -> Any:
        """Connect if needed and re-run the query to read live device state."""
        last_error: BaseException | None = None
        for attempt in range(1, 3):
            async with self._lock:
                try:
                    await self._ensure_connected_locked()
                    parsed = await self._query_locked()
                    return parsed
                except _RETRY_EXCEPTIONS as err:
                    last_error = err
                    await self._disconnect_locked()
            if attempt < 2:
                await asyncio.sleep(1.0)
        raise LightElfBluetoothError(str(last_error) if last_error else "Bluetooth query failed")

    async def _send_settings(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send the global device settings block, changing only requested fields."""
        async with self._lock:
            await self._ensure_connected_locked()
            if self._settings_state is None:
                await self._query_locked()
            current = self._settings_state
            xy = int(args.get("xy", current.xy if current else 0))
            dmx_address = int(args.get("dmx_address", current.dmx_address if current else 1))
            dmx_address = max(1, min(512, dmx_address))
            kwargs = {
                "dmx_address": dmx_address,
                "channel": current.channel if current else 0,
                "display_size": current.display_size if current else 10,
                "xy": xy,
                "red": current.red if current else 255,
                "green": current.green if current else 255,
                "blue": current.blue if current else 255,
                "light": current.light if current else 3,
                "cfg": current.cfg if current else 0,
                "power": current.power if current else 0,
                "brightness": current.brightness if current else 50,
                "grating": current.grating if current else 5,
                "password_status": current.password_status if current else 255,
                "password": current.password if current else 6688,
                "cmd_new_type": bool(self._features and self._features.cmd_new_type),
            }
            await self._write_script_locked(settings_command(**kwargs))
            if current is not None:
                self._settings_state = replace(current, xy=xy, dmx_address=dmx_address)
            return {"xy": xy, "dmx_address": dmx_address}

    async def _cancel_loop(self) -> None:
        if self._loop_task is None:
            return
        self._loop_task.cancel()
        try:
            await self._loop_task
        except asyncio.CancelledError:
            pass
        except Exception as err:
            LOGGER.debug("Native animation lock task ended with an error: %s", err)
        self._loop_task = None

    async def _native_lock_run(self, commands: list[str], interval: float) -> None:
        try:
            while True:
                await asyncio.sleep(max(interval, 0.25))
                await self._send_commands(commands)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._can_send = False
            raise

    async def request(self, cmd: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one native Bluetooth command and return a service-style response."""
        args = args or {}

        if self.discovery_active and cmd not in ("ping", "ble_state"):
            raise LightElfBluetoothError("Compatibility scan is running; try again when it finishes")

        if cmd == "ping":
            available = self._ble_device() is not None
            if not available:
                raise LightElfBluetoothError(f"{self.address} is not visible to HA Bluetooth")
            return {"ok": True, "message": "ok", "data": {"available": True}, "output": ""}

        if cmd == "ble_state":
            available = self._ble_device() is not None
            connected = bool(self._client is not None and self._client.is_connected)
            return {
                "ok": True,
                "message": "state",
                "data": {
                    "available": available,
                    "connected": connected,
                    "can_send": connected and self._can_send,
                    "device_on": self._device_on,
                    CONF_ADDRESS: self.address,
                    "transport": "bluetooth",
                },
                "output": "",
            }

        if cmd == "ble_connect":
            async with self._lock:
                await self._ensure_connected_locked()
            return {"ok": True, "message": "connected", "data": {}, "output": ""}

        if cmd == "ble_release":
            await self._cancel_loop()
            async with self._lock:
                await self._disconnect_locked()
            return {"ok": True, "message": "released", "data": {"connected": False}, "output": ""}

        if cmd == "query":
            parsed = await self._query_state()
            settings = self._settings_state
            return {
                "ok": True,
                "message": "query",
                "data": {
                    "available": True,
                    "connected": True,
                    "can_send": True,
                    "device_on": bool(parsed.device_on),
                    "device_type": parsed.device_type,
                    "version": parsed.version,
                    "ota_version": parsed.ota_version,
                    "device_number": parsed.device_number,
                    "user_number": parsed.user_number,
                    "settings_xy": settings.xy if settings else None,
                    "settings_dmx_address": settings.dmx_address if settings else None,
                    "mode_state": self._mode_state_data(),
                    CONF_ADDRESS: self.address,
                    "transport": "bluetooth",
                },
                "output": "",
            }

        if cmd == "raw":
            await self._cancel_loop()
            script = str(args.get("hex") or args.get("script") or "")
            if not script:
                raise LightElfBluetoothError("raw command requires a 'hex' payload")
            await self._send_commands([script])
            return {"ok": True, "message": "raw sent", "data": {}, "output": ""}

        if cmd == "power":
            await self._cancel_loop()
            on = bool(args.get("on", True))
            command = power_command(on, cmd_new_type=False)
            # Native firmware animations can occasionally ignore the first
            # power-off write while the effect engine is active. The command is
            # idempotent, so send OFF twice to make the light entity dependable.
            await self._send_commands([command] if on else [command, command])
            return {"ok": True, "message": "power", "data": {}, "output": ""}

        if cmd == "mode":
            await self._cancel_loop()
            await self._send_commands([mode_command(mode=args.get("mode", 0), **_mode_kwargs_from_args(args))])
            return {"ok": True, "message": "mode", "data": {}, "output": ""}

        if cmd == "settings":
            data = await self._send_settings(args)
            return {"ok": True, "message": "settings", "data": data, "output": ""}

        if cmd == "stop_motion":
            await self._cancel_loop()
            await self._send_commands([mode_command(mode=8, color=9)])
            return {"ok": True, "message": "playback stopped", "data": {"mode": 8}, "output": ""}

        if cmd == "builtin_native":
            await self._cancel_loop()
            commands, data = _native_builtin_commands(args)
            await self._send_commands(commands)
            if bool(args.get("loop", False)):
                interval = float(args.get("lock_interval", args.get("loop_interval", 0.75)))
                # Initial playback benefits from the app-style point-play clear
                # followed by C0 mode selection. Lock refreshes should only
                # reassert the C0 project bitmask; repeatedly sending the empty
                # point-play selector can make some firmware entries wander.
                lock_commands = commands[-1:]
                self._loop_task = self.hass.async_create_task(
                    self._native_lock_run(lock_commands, interval)
                )
                data["loop"] = True
                data["lock_interval"] = max(interval, 0.25)
            else:
                data["loop"] = False
            return {"ok": True, "message": "native", "data": data, "output": ""}

        if cmd in ("draw_text", "draw_text_font"):
            await self._cancel_loop()
            color = int(args.get("color", 7))
            size = int(args.get("height", args.get("size", 150)))
            await self._send_commands(
                [draw_text_command(str(args["text"]), size=size, color=color)]
            )
            return {"ok": True, "message": "draw_text ok", "data": {}, "output": ""}

        raise LightElfBluetoothError(f"Unsupported native Bluetooth command: {cmd}")

    async def ping(self) -> dict[str, Any]:
        """Ping the native Bluetooth path without opening a connection."""
        return await self.request("ping")
