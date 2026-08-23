"""Entity setup + behaviour tests for the Caldera Sauna integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_TEMPERATURE


async def test_entities_created(hass, setup_integration):
    entry, _ = setup_integration
    assert entry.state is ConfigEntryState.LOADED

    # One entity per platform (unique_ids anchored on the address).
    assert hass.states.get("climate.sauna_ble") is not None
    assert hass.states.get("switch.sauna_ble_cabin_lamp") is not None
    assert hass.states.get("light.sauna_ble_mood_light") is not None
    assert hass.states.get("number.sauna_ble_timer") is not None
    assert hass.states.get("binary_sensor.sauna_ble_problem") is not None


async def test_state_reflects_frame(hass, setup_integration):
    _, sauna = setup_integration
    climate = hass.states.get("climate.sauna_ble")
    # IDLE_FRAME: off, target 158, current 0, err 0
    assert climate.state == "off"
    assert climate.attributes["temperature"] == 158
    assert hass.states.get("binary_sensor.sauna_ble_problem").state == "off"


async def test_problem_sensor_trips_on_error(hass, setup_integration):
    _, sauna = setup_integration
    # 15 chars; power on (idx1='o'), err code 3 (idx13='3')
    sauna.push("xoff0000000003z")
    await hass.async_block_till_done()
    problem = hass.states.get("binary_sensor.sauna_ble_problem")
    assert problem.state == "on"
    assert problem.attributes["error_code"] == 3


async def test_set_temperature_sends_command(hass, setup_integration):
    _, sauna = setup_integration
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.sauna_ble", ATTR_TEMPERATURE: 150},
        blocking=True,
    )
    assert ("temp", 150) in sauna.commands


async def test_unload(hass, setup_integration):
    entry, _ = setup_integration
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
