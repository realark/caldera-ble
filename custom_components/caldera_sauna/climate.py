"""Climate entity: power (heat/off), current + target temperature, timer attr."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from caldera_sauna.protocol import TempUnit, model_from_name, temp_limits

from . import CalderaConfigEntry
from .entity import CalderaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CalderaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CalderaClimate(entry.runtime_data)])


class CalderaClimate(CalderaEntity, ClimateEntity):
    _attr_name = None  # use the device name for the main entity
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 1

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.address
        self._model = model_from_name(coordinator.sauna.name)

    @property
    def temperature_unit(self) -> str:
        state = self.coordinator.data
        if state and state.unit is TempUnit.FAHRENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    @property
    def _unit(self) -> TempUnit:
        state = self.coordinator.data
        return state.unit if state else TempUnit.CELSIUS

    @property
    def min_temp(self) -> float:
        return temp_limits(self._model, self._unit)[0]

    @property
    def max_temp(self) -> float:
        return temp_limits(self._model, self._unit)[1]

    @property
    def current_temperature(self) -> float | None:
        state = self.coordinator.data
        return state.current_temp if state else None

    @property
    def target_temperature(self) -> float | None:
        state = self.coordinator.data
        return state.target_temp if state else None

    @property
    def hvac_mode(self) -> HVACMode:
        state = self.coordinator.data
        return HVACMode.HEAT if state and state.power else HVACMode.OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if not state:
            return {}
        return {"timer_minutes": state.timer_minutes, "error_code": state.error}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.coordinator.sauna.async_set_target_temp(int(temp))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.sauna.async_set_power(hvac_mode is HVACMode.HEAT)

    async def async_turn_on(self) -> None:
        await self.coordinator.sauna.async_set_power(True)

    async def async_turn_off(self) -> None:
        await self.coordinator.sauna.async_set_power(False)
