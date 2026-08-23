"""Light entity: the RGB mood light (on/off + color preset as 'effect').

The presets are exposed as effects rather than true RGB because the module only
accepts a preset index. The Color enum already carries the real observed color
names (the OEM app's labels are scrambled), so EFFECTS derives straight from it.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity, LightEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from caldera_sauna.protocol import Color

from . import CalderaConfigEntry
from .entity import CalderaEntity

# effect label -> protocol Color index, from the (observed-correct) Color enum.
EFFECTS: dict[str, Color] = {c.name.title(): c for c in Color}
_INDEX_TO_LABEL = {c: label for label, c in EFFECTS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalderaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CalderaColorLight(entry.runtime_data)])


class CalderaColorLight(CalderaEntity, LightEntity):
    _attr_translation_key = "color_light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = list(EFFECTS)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_color"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        return state.color_on if state else None

    @property
    def effect(self) -> str | None:
        state = self.coordinator.data
        if state and state.color is not None:
            return _INDEX_TO_LABEL.get(state.color)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        effect = kwargs.get("effect")
        if effect is not None and effect in EFFECTS:
            # Ensure it's on, then select the preset.
            if not (self.coordinator.data and self.coordinator.data.color_on):
                await self.coordinator.sauna.async_set_color_light(True)
            await self.coordinator.sauna.async_set_color(EFFECTS[effect])
        else:
            await self.coordinator.sauna.async_set_color_light(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.sauna.async_set_color_light(False)
