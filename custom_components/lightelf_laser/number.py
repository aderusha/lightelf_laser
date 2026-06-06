"""Number entities for the LightElf Laser integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    SOUND_SENSITIVITY_MAX,
    SOUND_SENSITIVITY_MIN,
    TEXT_SIZE_MAX,
    TEXT_SIZE_MIN,
    TEXT_Y_MAX,
    TEXT_Y_MIN,
)
from .coordinator import EytseLaserConfigEntry
from .entity import EytseLaserEntity


@dataclass(frozen=True, kw_only=True)
class EytseNumberDescription(NumberEntityDescription):
    """Number metadata."""

    attr: str
    minimum: float
    maximum: float
    step: float = 1
    slider: bool = False
    # When set, max comes from this coordinator property at runtime (count-1).
    dynamic_max_attr: str | None = None


NUMBERS = (
    EytseNumberDescription(
        key="text_size",
        name="Text size",
        icon="mdi:format-size",
        attr="text_size",
        minimum=TEXT_SIZE_MIN,
        maximum=TEXT_SIZE_MAX,
        step=10,
    ),
    EytseNumberDescription(
        key="text_y",
        name="Text vertical position",
        icon="mdi:arrow-up-down",
        attr="text_y",
        minimum=TEXT_Y_MIN,
        maximum=TEXT_Y_MAX,
        step=10,
    ),
    EytseNumberDescription(
        key="shape_index",
        name="Shape index",
        icon="mdi:counter",
        attr="builtin_index",
        minimum=0,
        maximum=255,
        step=1,
        dynamic_max_attr="builtin_count",
    ),
    EytseNumberDescription(
        key="scroll_speed",
        name="Scroll speed",
        icon="mdi:speedometer",
        attr="scroll_speed",
        minimum=1,
        maximum=100,
        step=1,
    ),
    EytseNumberDescription(
        key="animation_index",
        name="Animation index",
        icon="mdi:counter",
        attr="native_animation_index",
        minimum=1,
        maximum=64,
        step=1,
        dynamic_max_attr="native_animation_count",
    ),
    EytseNumberDescription(
        key="animation_speed",
        name="Animation speed",
        icon="mdi:speedometer",
        attr="native_animation_speed",
        minimum=1,
        maximum=100,
        step=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EytseLaserConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = config_entry.runtime_data
    entities: list[NumberEntity] = [
        EytseNumber(coordinator, description) for description in NUMBERS
    ]
    entities.append(EytseSoundSensitivityNumber(coordinator))
    async_add_entities(entities)


class EytseNumber(EytseLaserEntity, NumberEntity):
    """A configurable laser parameter held locally until the next draw."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, description: EytseNumberDescription) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_name = description.name
        self._attr_native_min_value = description.minimum
        self._attr_native_max_value = description.maximum
        self._attr_native_step = description.step
        if description.slider:
            self._attr_mode = NumberMode.SLIDER

    @property
    def available(self) -> bool:
        """Editable even when the radio is released."""
        return True

    @property
    def native_max_value(self) -> float:
        """Dynamic max for index numbers (family count - 1), else static."""
        if self.entity_description.dynamic_max_attr:
            offset = 1 if self.entity_description.minimum == 0 else 0
            return float(
                max(
                    self.entity_description.minimum,
                    getattr(self.coordinator, self.entity_description.dynamic_max_attr) - offset,
                )
            )
        return self.entity_description.maximum

    @property
    def native_value(self) -> float:
        """Return current value."""
        value = getattr(self.coordinator, self.entity_description.attr)
        if float(value).is_integer():
            return int(value)
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Store the value for subsequent draws."""
        value = int(value)
        if self.entity_description.dynamic_max_attr:
            value = max(
                int(self.entity_description.minimum),
                min(value, int(self.native_max_value)),
            )
        setattr(self.coordinator, self.entity_description.attr, value)
        self.coordinator.async_update_listeners()


class EytseSoundSensitivityNumber(EytseLaserEntity, NumberEntity):
    """Onboard-mic sensitivity for sound-reactive ("Music") playback.

    Persisted in entry.options via the coordinator; re-applied live when sound
    mode is on and a firmware effect is playing.
    """

    _attr_name = "Sound sensitivity"
    _attr_icon = "mdi:microphone"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = SOUND_SENSITIVITY_MIN
    _attr_native_max_value = SOUND_SENSITIVITY_MAX
    _attr_native_step = 1

    def __init__(self, coordinator) -> None:
        """Initialize the sensitivity slider."""
        super().__init__(coordinator, "sound_sensitivity")

    @property
    def available(self) -> bool:
        """Editable even when the radio is released (applied on next play)."""
        return True

    @property
    def native_value(self) -> float:
        """Return the current sensitivity."""
        return int(self.coordinator.sound_sensitivity)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the sensitivity and re-apply if sound mode is active."""
        await self.coordinator.async_set_sound_sensitivity(int(value))
