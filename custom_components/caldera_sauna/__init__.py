"""The Caldera Sauna integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .coordinator import CalderaCoordinator

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SWITCH,
]

CalderaConfigEntry = ConfigEntry[CalderaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CalderaConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    coordinator = CalderaCoordinator(hass, entry, address)
    await coordinator.async_start()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CalderaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: CalderaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
