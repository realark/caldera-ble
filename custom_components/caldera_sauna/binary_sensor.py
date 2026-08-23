"""Binary sensor: sauna fault/problem, derived from the status frame's error code."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CalderaConfigEntry
from .entity import CalderaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalderaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([CalderaProblem(entry.runtime_data)])


class CalderaProblem(CalderaEntity, BinarySensorEntity):
    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_problem"

    @property
    def is_on(self) -> bool | None:
        state = self.coordinator.data
        return (not state.ok) if state else None

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        state = self.coordinator.data
        return {"error_code": state.error} if state else {}
