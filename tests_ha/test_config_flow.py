"""Config flow tests: manual (user) step discovery and duplicate guard."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.caldera_sauna.const import DOMAIN

from .conftest import ADDRESS

DISCOVERED = [SimpleNamespace(address=ADDRESS, name="Sauna-BLE")]


async def test_user_flow_creates_entry(hass):
    with patch(
        "custom_components.caldera_sauna.config_flow.async_discovered_service_info",
        return_value=DISCOVERED,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: ADDRESS}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS}


async def test_user_flow_no_devices_aborts(hass):
    with patch(
        "custom_components.caldera_sauna.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_duplicate_address_aborts(hass):
    MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}
    ).add_to_hass(hass)

    with patch(
        "custom_components.caldera_sauna.config_flow.async_discovered_service_info",
        return_value=DISCOVERED,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    # The only candidate is already configured, so nothing new to add.
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"
