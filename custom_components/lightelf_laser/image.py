"""Image entities for the LightElf Laser integration."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import LightElfLaserConfigEntry
from .entity import LightElfLaserEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: LightElfLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up preview image entities."""
    coordinator = config_entry.runtime_data
    async_add_entities(
        [
            LightElfSvgPreview(coordinator, hass),
            LightElfTextPreview(coordinator, hass),
            LightElfShapePreview(coordinator, hass),
            LightElfNativeAnimationPreview(coordinator, hass),
        ]
    )


class _PngPreviewBase(LightElfLaserEntity, ImageEntity):
    """Base class for generated PNG previews."""

    _attr_content_type = "image/png"

    def __init__(self, coordinator, hass: HomeAssistant, key: str) -> None:
        """Initialize the preview image."""
        super().__init__(coordinator, key)
        ImageEntity.__init__(self, hass)
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def available(self) -> bool:
        """Generated previews are available without BLE."""
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        """Bump the image timestamp so HA re-fetches when inputs change."""
        self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()


class LightElfSvgPreview(_PngPreviewBase):
    """Local preview of the currently-selected SVG."""

    _attr_name = "SVG preview"

    def __init__(self, coordinator, hass: HomeAssistant) -> None:
        """Initialize the preview image."""
        super().__init__(coordinator, hass, "svg_preview")

    async def async_image(self) -> bytes | None:
        """Return PNG bytes for the selected SVG."""
        return await self.coordinator.async_read_svg_preview()


class LightElfTextPreview(_PngPreviewBase):
    """Local preview of the current text settings."""

    _attr_name = "Text preview"

    def __init__(self, coordinator, hass: HomeAssistant) -> None:
        """Initialize the preview image."""
        super().__init__(coordinator, hass, "text_preview")

    async def async_image(self) -> bytes | None:
        """Return PNG bytes for the current text settings."""
        return await self.coordinator.async_read_text_preview()


class LightElfShapePreview(_PngPreviewBase):
    """Live preview of the currently-selected built-in shape."""

    _attr_name = "Shape preview"

    def __init__(self, coordinator, hass: HomeAssistant) -> None:
        """Initialize the preview image."""
        super().__init__(coordinator, hass, "shape_preview")

    async def async_image(self) -> bytes | None:
        """Return PNG bytes for the selected shape."""
        return await self.coordinator.async_read_shape_thumb()


class LightElfNativeAnimationPreview(LightElfLaserEntity, ImageEntity):
    """Captured preview of the currently-selected firmware-native animation."""

    _attr_name = "Animation preview"

    def __init__(self, coordinator, hass: HomeAssistant) -> None:
        """Initialize the preview image."""
        super().__init__(coordinator, "animation_preview")
        ImageEntity.__init__(self, hass)
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def available(self) -> bool:
        """The preview is a local picture; always show the entity."""
        return True

    @property
    def content_type(self) -> str:
        """Return the selected preview image type."""
        path = self.coordinator.native_animation_thumb_path
        if path is not None and path.suffix.lower() == ".webp":
            return "image/webp"
        if path is not None and path.suffix.lower() == ".gif":
            return "image/gif"
        if path is not None and path.suffix.lower() == ".png":
            return "image/png"
        return "image/jpeg"

    async def async_image(self) -> bytes | None:
        """Return JPEG bytes for the selected native animation preview."""
        return await self.coordinator.async_read_native_animation_thumb()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Bump the image timestamp so HA re-fetches when selection changes."""
        self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
