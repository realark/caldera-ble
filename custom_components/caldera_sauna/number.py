"""Number entity: the session timer (minutes)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from caldera_sauna.protocol import TIMER_MAX, TIMER_MIN

from . import CalderaConfigEntry
from .entity import CalderaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalderaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([CalderaTimer(entry.runtime_data)])


class CalderaTimer(CalderaEntity, NumberEntity):
    _attr_translation_key = "timer"
    _attr_icon = "mdi:timer"
    _attr_native_min_value = TIMER_MIN
    _attr_native_max_value = TIMER_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_timer"

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.data
        return state.timer_minutes if state else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.sauna.async_set_timer(int(value))
