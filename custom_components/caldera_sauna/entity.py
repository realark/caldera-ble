"""Shared base entity for Caldera Sauna platforms."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CalderaCoordinator


class CalderaEntity(CoordinatorEntity[CalderaCoordinator]):
    """Base with shared device info; entities read from coordinator.data."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CalderaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="Relaxe / Caldera",
            name=coordinator.sauna.name or "Sauna",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
