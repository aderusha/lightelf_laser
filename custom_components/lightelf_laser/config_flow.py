"""Config flow for the LightElf Laser integration."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any
import xml.etree.ElementTree as ET

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector
from homeassistant.util import raise_if_invalid_filename

from .const import (
    CONF_NAME,
    CONF_TIMEOUT,
    DEFAULT_ADDRESS,
    DEFAULT_NAME,
    DEFAULT_TIMEOUT,
    DOMAIN,
    LIGHTELF_SERVICE_UUIDS,
    SVG_MEDIA_SUBDIR,
    TRANSPORT_BLUETOOTH,
)


CONF_SVG_FILE = "svg_file"

UPLOAD_SVG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SVG_FILE): selector.FileSelector(
            selector.FileSelectorConfig(accept=".svg,image/svg+xml")
        ),
    }
)


def _resolve_svg_media_dir(hass) -> Path:
    """Return the HA local-media SVG upload directory."""
    media_root = Path("/media")
    if media_root.exists():
        return media_root / SVG_MEDIA_SUBDIR
    media_dirs = getattr(hass.config, "media_dirs", {}) or {}
    local_media = media_dirs.get("local") if isinstance(media_dirs, dict) else None
    if local_media:
        return Path(local_media) / SVG_MEDIA_SUBDIR
    return Path(hass.config.path("media")) / SVG_MEDIA_SUBDIR


def _save_uploaded_svg(hass, uploaded_file_id: str) -> str:
    """Validate an uploaded SVG and save it into the integration media folder."""
    with process_uploaded_file(hass, uploaded_file_id) as file_path:
        filename = file_path.name
        raise_if_invalid_filename(filename)
        if file_path.suffix.lower() != ".svg":
            raise ValueError("uploaded file must have a .svg extension")
        root = ET.parse(file_path).getroot()
        if root.tag.rsplit("}", 1)[-1].lower() != "svg":
            raise ValueError("uploaded file is not an SVG")
        target_dir = _resolve_svg_media_dir(hass)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        shutil.copyfile(file_path, target)
        return filename


class LightElfLaserConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a LightElf Laser config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Create the options flow."""
        return LightElfLaserOptionsFlow()

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or DEFAULT_NAME,
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Bluetooth discovery."""
        assert self._discovery_info is not None
        if user_input is None:
            return self.async_show_form(
                step_id="bluetooth_confirm",
                description_placeholders={
                    "name": self._discovery_info.name or self._discovery_info.address,
                },
            )
        return await self._async_create_bluetooth_entry(
            DEFAULT_NAME,
            self._discovery_info.address,
            DEFAULT_TIMEOUT,
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            if bluetooth.async_ble_device_from_address(
                self.hass, address, connectable=True
            ) is None:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_create_bluetooth_entry(
                    user_input[CONF_NAME],
                    address,
                    float(user_input[CONF_TIMEOUT]),
                )

        current_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass):
            if discovery_info.address in current_addresses:
                continue
            service_uuids = {uuid.lower() for uuid in discovery_info.service_uuids}
            if not service_uuids.intersection(LIGHTELF_SERVICE_UUIDS):
                continue
            self._discovered_devices[discovery_info.address] = discovery_info

        address_default = DEFAULT_ADDRESS
        if self._discovered_devices:
            address_default = next(iter(self._discovered_devices))

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_ADDRESS, default=address_default): str,
                    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
                        vol.Coerce(float), vol.Range(min=1, max=60)
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_create_bluetooth_entry(
        self,
        name: str,
        address: str,
        timeout: float,
    ) -> ConfigFlowResult:
        """Create a native Bluetooth config entry."""
        await self.async_set_unique_id(address, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=name,
            data={
                CONF_NAME: name,
                "transport": TRANSPORT_BLUETOOTH,
                CONF_ADDRESS: address,
                CONF_TIMEOUT: timeout,
            },
        )


class LightElfLaserOptionsFlow(OptionsFlow):
    """Handle LightElf Laser options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Upload an SVG into the integration media folder."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                filename = await self.hass.async_add_executor_job(
                    _save_uploaded_svg, self.hass, user_input[CONF_SVG_FILE]
                )
            except (ET.ParseError, OSError, ValueError):
                errors["base"] = "invalid_svg"
            else:
                coordinator = getattr(self.config_entry, "runtime_data", None)
                if coordinator is not None:
                    await coordinator.async_rescan_svgs()
                    coordinator.selected_svg = filename
                    coordinator.async_update_listeners()
                return self.async_create_entry(
                    title="",
                    data=dict(self.config_entry.options),
                )

        return self.async_show_form(
            step_id="init",
            data_schema=UPLOAD_SVG_SCHEMA,
            errors=errors,
        )
