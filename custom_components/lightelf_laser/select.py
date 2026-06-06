"""Select entities for the LightElf Laser integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    COLOR_OPTIONS,
    MOUNT_ORIENTATION_OPTIONS,
    NATIVE_ANIMATION_FAMILIES,
    SHAPE_COLOR_OPTIONS,
    SVG_COLOR_OPTIONS,
    TEXT_COLOR_OPTIONS,
    TEXT_MODES,
)
from .coordinator import EytseLaserConfigEntry
from .entity import EytseLaserEntity

_NONE = "(no SVG files found)"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EytseLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator = config_entry.runtime_data
    await coordinator.async_rescan_svgs()
    async_add_entities(
        [
            EytseSvgSelect(coordinator),
            EytseSvgColorSelect(coordinator),
            EytseTextFontSelect(coordinator),
            EytseTextColorSelect(coordinator),
            EytseShapeFamilySelect(coordinator),
            EytseShapeColorSelect(coordinator),
            EytseNativeAnimationFamilySelect(coordinator),
            EytseTextModeSelect(coordinator),
            EytseMountOrientationSelect(coordinator),
        ]
    )


class EytseSvgSelect(EytseLaserEntity, SelectEntity):
    """Pick which SVG file the Show SVG button will draw."""

    _attr_name = "SVG image"
    _attr_icon = "mdi:vector-square"

    def __init__(self, coordinator) -> None:
        """Initialize the selector."""
        super().__init__(coordinator, "svg_image")

    @property
    def available(self) -> bool:
        """The picker stays usable so files can be chosen before connecting."""
        return True

    @property
    def options(self) -> list[str]:
        """Return the SVG files currently in the drop folder."""
        return self.coordinator.available_svgs or [_NONE]

    @property
    def current_option(self) -> str | None:
        """Return the selected SVG, or the placeholder when none exist."""
        if not self.coordinator.available_svgs:
            return _NONE
        return self.coordinator.selected_svg

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen SVG file."""
        if option == _NONE:
            return
        self.coordinator.selected_svg = option
        self.coordinator.async_update_listeners()


class EytseSvgColorSelect(EytseLaserEntity, SelectEntity):
    """SVG color: 'original' preserves SVG stroke colors, or force one color."""

    _attr_name = "SVG color"
    _attr_icon = "mdi:palette"
    _attr_options = list(SVG_COLOR_OPTIONS)

    def __init__(self, coordinator) -> None:
        """Initialize the color selector."""
        super().__init__(coordinator, "svg_color")

    @property
    def available(self) -> bool:
        """Selectable even when the radio is released."""
        return True

    @property
    def current_option(self) -> str:
        """Return the selected SVG color mode."""
        return self.coordinator.svg_color

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen SVG color mode."""
        self.coordinator.svg_color = option
        self.coordinator.async_update_listeners()


class EytseTextFontSelect(EytseLaserEntity, SelectEntity):
    """Pick the Hershey vector font used to draw text."""

    _attr_name = "Text font"
    _attr_icon = "mdi:format-font"

    def __init__(self, coordinator) -> None:
        """Initialize the font selector."""
        super().__init__(coordinator, "text_font")

    @property
    def available(self) -> bool:
        """Selectable even when the radio is released."""
        return True

    @property
    def options(self) -> list[str]:
        """Return the bundled font names."""
        return self.coordinator.available_fonts or [self.coordinator.text_font]

    @property
    def current_option(self) -> str:
        """Return the selected font."""
        return self.coordinator.text_font

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen font."""
        self.coordinator.text_font = option
        self.coordinator.async_update_listeners()


class EytseTextColorSelect(EytseLaserEntity, SelectEntity):
    """Pick the beam color used to draw text (solid, or rainbow per stroke)."""

    _attr_name = "Text color"
    _attr_icon = "mdi:palette"
    _attr_options = list(TEXT_COLOR_OPTIONS)

    def __init__(self, coordinator) -> None:
        """Initialize the color selector."""
        super().__init__(coordinator, "text_color")

    @property
    def available(self) -> bool:
        """Selectable even when the radio is released."""
        return True

    @property
    def current_option(self) -> str:
        """Return the selected color."""
        return self.coordinator.text_color

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen color."""
        self.coordinator.text_color = option
        self.coordinator.async_update_listeners()


class EytseShapeFamilySelect(EytseLaserEntity, SelectEntity):
    """Pick the built-in shape family to browse."""

    _attr_name = "Shape family"
    _attr_icon = "mdi:shape"

    def __init__(self, coordinator) -> None:
        """Initialize the family selector."""
        super().__init__(coordinator, "shape_family")

    @property
    def available(self) -> bool:
        """Browsable even when the radio is released."""
        return True

    @property
    def options(self) -> list[str]:
        """Return the built-in shape families."""
        return self.coordinator.builtin_families or [self.coordinator.builtin_family]

    @property
    def current_option(self) -> str:
        """Return the selected family."""
        return self.coordinator.builtin_family

    async def async_select_option(self, option: str) -> None:
        """Select a family and clamp the index into it."""
        self.coordinator.builtin_family = option
        self.coordinator.builtin_index = min(
            self.coordinator.builtin_index, self.coordinator.builtin_count - 1
        )
        self.coordinator.async_update_listeners()


class EytseShapeColorSelect(EytseLaserEntity, SelectEntity):
    """Shape color: 'original' keeps the shape's own colors, or force one color."""

    _attr_name = "Shape color"
    _attr_icon = "mdi:palette"
    _attr_options = list(SHAPE_COLOR_OPTIONS)

    def __init__(self, coordinator) -> None:
        """Initialize the color selector."""
        super().__init__(coordinator, "shape_color")

    @property
    def available(self) -> bool:
        """Selectable even when the radio is released."""
        return True

    @property
    def current_option(self) -> str:
        """Return the selected color."""
        return self.coordinator.builtin_color

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen color."""
        self.coordinator.builtin_color = option
        self.coordinator.async_update_listeners()


class EytseNativeAnimationFamilySelect(EytseLaserEntity, SelectEntity):
    """Pick the firmware-native animation/effect family to play."""

    _attr_name = "Animation family"
    _attr_icon = "mdi:animation-play"
    _attr_options = list(NATIVE_ANIMATION_FAMILIES)

    def __init__(self, coordinator) -> None:
        """Initialize the family selector."""
        super().__init__(coordinator, "animation_family")

    @property
    def available(self) -> bool:
        """Selectable even when the radio is released."""
        return True

    @property
    def current_option(self) -> str:
        """Return the selected animation family."""
        return self.coordinator.native_animation_family

    async def async_select_option(self, option: str) -> None:
        """Select a family and clamp the one-based index into it."""
        self.coordinator.native_animation_family = option
        self.coordinator.native_animation_index = min(
            self.coordinator.native_animation_index,
            self.coordinator.native_animation_count,
        )
        self.coordinator.async_update_listeners()


class EytseTextModeSelect(EytseLaserEntity, SelectEntity):
    """How the Show Text button shows text: static, or scrolling by direction."""

    _attr_name = "Text mode"
    _attr_icon = "mdi:format-text-rotation-none"
    _attr_options = list(TEXT_MODES)

    def __init__(self, coordinator) -> None:
        """Initialize the text-mode selector."""
        super().__init__(coordinator, "text_mode")

    @property
    def available(self) -> bool:
        """Selectable even when the radio is released."""
        return True

    @property
    def current_option(self) -> str:
        """Return the selected text mode."""
        return self.coordinator.text_mode

    async def async_select_option(self, option: str) -> None:
        """Remember the chosen text mode."""
        self.coordinator.text_mode = option
        self.coordinator.async_update_listeners()


class EytseMountOrientationSelect(EytseLaserEntity, SelectEntity):
    """Pick the projector-global mount orientation from the app presets."""

    _attr_name = "Mount orientation"
    _attr_icon = "mdi:axis-arrow"
    _attr_options = list(MOUNT_ORIENTATION_OPTIONS)

    def __init__(self, coordinator) -> None:
        """Initialize the mount-orientation selector."""
        super().__init__(coordinator, "mount_orientation")

    @property
    def current_option(self) -> str | None:
        """Return the current app preset label."""
        current = self.coordinator.mount_orientation
        return current if current in MOUNT_ORIENTATION_OPTIONS else None

    async def async_select_option(self, option: str) -> None:
        """Set the projector-global mount orientation."""
        await self.coordinator.async_set_mount_xy(MOUNT_ORIENTATION_OPTIONS[option])
