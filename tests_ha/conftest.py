"""Fixtures for the Home Assistant integration tests.

These require the extra test deps (pytest-homeassistant-custom-component) and are
run separately from the pure-library suite:

    pytest tests_ha/
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from caldera_sauna.protocol import parse_status
from custom_components.caldera_sauna.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"

ADDRESS = "AA:BB:CC:DD:EE:FF"
# A realistic status frame: off, °F, target 158, timer 49, err 0.
IDLE_FRAME = "xfff01000319e0z"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let HA load our custom component during tests."""
    yield


class FakeSauna:
    """Stand-in for caldera_sauna.device.CalderaSauna — no real Bluetooth.

    Captures the coordinator's state callback so tests can push status frames,
    and records the last command written.
    """

    def __init__(self, ble_device, state_callback=None, connection_callback=None,
                 device_provider=None):
        self.name = getattr(ble_device, "name", "Sauna-BLE")
        self._state_cb = state_callback
        self.state = None
        self.commands: list[tuple] = []

    async def start(self):
        # Emit one frame on connect so entities become available.
        self.push(IDLE_FRAME)

    async def stop(self):
        pass

    def push(self, frame: str):
        self.state = parse_status(frame)
        if self._state_cb is not None:
            self._state_cb(self.state)

    # command methods the entities call
    async def async_set_power(self, on):
        self.commands.append(("power", on))

    async def async_set_lamp(self, on):
        self.commands.append(("lamp", on))

    async def async_set_color_light(self, on):
        self.commands.append(("color_light", on))

    async def async_set_color(self, color):
        self.commands.append(("color", int(color)))

    async def async_set_target_temp(self, value):
        self.commands.append(("temp", value))

    async def async_set_timer(self, minutes):
        self.commands.append(("timer", minutes))


@pytest.fixture
async def setup_integration(hass):
    """Set up the integration with a fake device; return (entry, FakeSauna)."""
    # The sauna reports °F; keep the test's unit system imperial so HA doesn't
    # convert displayed temperatures to °C.
    hass.config.units = US_CUSTOMARY_SYSTEM

    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)

    fake = {}
    fake_device = SimpleNamespace(address=ADDRESS, name="Sauna-BLE")

    def make_sauna(ble_device, **kwargs):
        fake["sauna"] = FakeSauna(ble_device, **kwargs)
        return fake["sauna"]

    with patch(
        "custom_components.caldera_sauna.coordinator.bluetooth."
        "async_ble_device_from_address",
        return_value=fake_device,
    ), patch(
        "custom_components.caldera_sauna.coordinator.CalderaSauna", make_sauna
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry, fake["sauna"]
