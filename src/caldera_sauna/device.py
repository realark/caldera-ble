"""BLE transport for the Caldera sauna, built on bleak-retry-connector.

Using ``establish_connection`` (rather than raw ``BleakClient``) is what lets
this same code path work transparently through ESPHome BLE proxies inside Home
Assistant. The class keeps a persistent connection and pushes decoded
``SaunaState`` snapshots to a callback as the sauna notifies.

Commands are only sent by the explicit ``async_*`` methods; construction and
``start()`` never write, so monitoring is inherently read-only.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from . import protocol as p
from .protocol import Color, SaunaState

_LOGGER = logging.getLogger(__name__)

# Confirmed on the Sauna-BLE hardware (see PROTOCOL.md).
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# Candidate combined write+notify chars for other module variants.
_CHAR_FALLBACKS = (
    CHAR_UUID,
    "0000ffe1-0000-1000-8000-00805f9b34fb",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",  # NUS TX (write); RX is …0003
)

StateCallback = Callable[[SaunaState], None]


class CalderaSauna:
    def __init__(
        self,
        ble_device: BLEDevice,
        state_callback: StateCallback | None = None,
    ) -> None:
        self._device = ble_device
        self._client: BleakClient | None = None
        self._char = None
        self._state_cb = state_callback
        self._state: SaunaState | None = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str | None:
        return self._device.name

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def state(self) -> SaunaState | None:
        return self._state

    async def start(self) -> None:
        """Connect and subscribe to status notifications. Sends nothing."""
        client = await establish_connection(
            BleakClient, self._device, self._device.address
        )
        self._client = client
        self._char = self._resolve_char(client)
        await client.start_notify(self._char, self._on_notify)
        _LOGGER.info("Connected to %s (%s)", self.name, self.address)

    def _resolve_char(self, client: BleakClient):
        for uuid in _CHAR_FALLBACKS:
            ch = client.services.get_characteristic(uuid)
            if ch is not None:
                return ch
        raise RuntimeError("No known sauna write/notify characteristic found")

    def _on_notify(self, _char, data: bytearray) -> None:
        state = p.parse_status(bytes(data))
        if state is None:
            _LOGGER.debug("Ignoring non-status notify: %r", bytes(data))
            return
        self._state = state
        if self._state_cb is not None:
            self._state_cb(state)

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None

    async def _write(self, payload: bytes) -> None:
        if self._client is None or self._char is None:
            raise RuntimeError("Not connected")
        async with self._lock:
            await self._client.write_gatt_char(self._char, payload, response=True)

    # --- Commands -----------------------------------------------------------

    async def async_set_power(self, on: bool) -> None:
        await self._write(p.cmd_power(on))

    async def async_set_lamp(self, on: bool) -> None:
        await self._write(p.cmd_lamp(on))

    async def async_set_color_light(self, on: bool) -> None:
        await self._write(p.cmd_color_light(on))

    async def async_set_color(self, color: Color | int) -> None:
        await self._write(p.cmd_set_color(color))

    async def async_set_target_temp(self, value: int) -> None:
        await self._write(p.cmd_set_target_temp(value))

    async def async_set_timer(self, minutes: int) -> None:
        await self._write(p.cmd_set_timer(minutes))
