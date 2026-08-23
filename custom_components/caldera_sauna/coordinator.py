"""Connection coordinator: bridges HA Bluetooth to the caldera_sauna library.

Push model — the sauna streams status frames, so there is no polling interval.
The BLE device object comes from HA's Bluetooth stack, which is what lets the
connection route through ESPHome BLE proxies transparently.
"""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from caldera_sauna.device import CalderaSauna
from caldera_sauna.protocol import SaunaState

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CalderaCoordinator(DataUpdateCoordinator[SaunaState]):
    """Owns the persistent BLE connection and publishes decoded state."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, address: str
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self._entry = entry
        self._address = address
        self._sauna: CalderaSauna | None = None

    @property
    def address(self) -> str:
        return self._address

    @property
    def sauna(self) -> CalderaSauna:
        assert self._sauna is not None
        return self._sauna

    async def async_start(self) -> None:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if ble_device is None:
            raise ConfigEntryNotReady(
                f"Sauna {self._address} not currently seen by Bluetooth. "
                "Is it powered on and not connected to the phone app?"
            )
        self._sauna = CalderaSauna(ble_device, state_callback=self._on_state)
        await self._sauna.start()

    def _on_state(self, state: SaunaState) -> None:
        # Called from the BLE notify callback; hop onto the event loop.
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, state)

    async def async_stop(self) -> None:
        if self._sauna is not None:
            await self._sauna.stop()
            self._sauna = None
