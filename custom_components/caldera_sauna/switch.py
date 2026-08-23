"""Switch entity: the cabin lamp."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CalderaConfigEntry
from .entity import CalderaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalderaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([CalderaLamp(entry.runtime_data)])


class CalderaLamp(CalderaEntity, SwitchEntity):
    _attr_translation_key = "lamp"
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_lamp"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        return state.lamp if state else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.sauna.async_set_lamp(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.sauna.async_set_lamp(False)
