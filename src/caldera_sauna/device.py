"""BLE transport for the Caldera sauna, built on bleak-retry-connector.

Using ``establish_connection`` (rather than raw ``BleakClient``) is what lets
this same code path work transparently through ESPHome BLE proxies inside Home
Assistant. The class keeps a persistent connection, auto-reconnects with
backoff if the link drops, and pushes decoded ``SaunaState`` snapshots to a
callback as the sauna notifies.

Commands are only sent by the explicit ``async_*`` methods; construction and
``start()`` never write, so monitoring is inherently read-only.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
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

_RECONNECT_MIN_DELAY = 3.0
_RECONNECT_MAX_DELAY = 300.0

# When a command is issued while the link is briefly down, wait this long for
# the background reconnect to restore it before giving up.
_WRITE_RETRY_WAIT = 10.0

StateCallback = Callable[[SaunaState], None]
ConnectionCallback = Callable[[bool], None]
DeviceProvider = Callable[[], BLEDevice | None]


class CalderaSauna:
    def __init__(
        self,
        ble_device: BLEDevice,
        state_callback: StateCallback | None = None,
        connection_callback: ConnectionCallback | None = None,
        device_provider: DeviceProvider | None = None,
    ) -> None:
        """``device_provider``, if given, is called to fetch a fresh BLEDevice
        before each (re)connect attempt — pass one in Home Assistant so the
        connection follows address rotation and BLE proxies."""
        self._device = ble_device
        self._device_provider = device_provider
        self._state_cb = state_callback
        self._connection_cb = connection_callback
        self._client: BleakClient | None = None
        self._char = None
        self._state: SaunaState | None = None
        self._lock = asyncio.Lock()
        self._closing = False
        self._reconnect_task: asyncio.Task | None = None
        self._reconnect_wake: asyncio.Event | None = None
        self._reconnect_delay = _RECONNECT_MIN_DELAY
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def name(self) -> str | None:
        return self._device.name

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def state(self) -> SaunaState | None:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def start(self) -> None:
        """Connect and subscribe to status notifications. Sends nothing."""
        self._closing = False
        self._loop = asyncio.get_running_loop()
        self._reconnect_wake = asyncio.Event()
        await self._connect()

    def _current_device(self) -> BLEDevice:
        if self._device_provider is not None:
            fresh = self._device_provider()
            if fresh is not None:
                self._device = fresh
        return self._device

    async def _connect(self) -> None:
        device = self._current_device()
        client = await establish_connection(
            BleakClient,
            device,
            device.address,
            disconnected_callback=self._on_disconnected,
            ble_device_callback=self._current_device,
        )
        self._client = client
        self._char = self._resolve_char(client)
        await client.start_notify(self._char, self._on_notify)
        _LOGGER.info("Connected to %s (%s)", self.name, self.address)
        if self._connection_cb is not None:
            self._connection_cb(True)

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

    def _on_disconnected(self, _client: BleakClient) -> None:
        _LOGGER.info("Disconnected from %s", self.address)
        if self._connection_cb is not None:
            self._connection_cb(False)
        if self._closing or self._loop is None:
            return
        # Called from the BLE backend; schedule the reconnect on the loop.
        self._loop.call_soon_threadsafe(self._schedule_reconnect)

    def _schedule_reconnect(self) -> None:
        if self._closing:
            return
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = self._loop.create_task(self._reconnect_loop())

    def request_reconnect(self) -> None:
        """Nudge the reconnect loop to attempt a connection right now.

        Home Assistant calls this when its Bluetooth stack sees the sauna
        advertise again: rather than waiting out the exponential backoff, retry
        immediately and reset the backoff, since the device is evidently in
        range. Must be called from the event loop thread. No-op if already
        connected, not started, or closing.
        """
        if self._closing or self._loop is None or self.is_connected:
            return
        self._reconnect_delay = _RECONNECT_MIN_DELAY
        self._schedule_reconnect()
        if self._reconnect_wake is not None:
            self._reconnect_wake.set()

    async def _reconnect_loop(self) -> None:
        self._reconnect_delay = _RECONNECT_MIN_DELAY
        while not self._closing:
            # Wait out the backoff, but wake early if an advertisement nudge
            # (request_reconnect) arrives — the device just came back in range.
            if self._reconnect_wake is not None:
                try:
                    await asyncio.wait_for(
                        self._reconnect_wake.wait(), self._reconnect_delay
                    )
                except TimeoutError:
                    pass
                self._reconnect_wake.clear()
            else:
                await asyncio.sleep(self._reconnect_delay)
            if self._closing:
                return
            if self.is_connected:
                return
            try:
                await self._connect()
                return
            except Exception as err:  # noqa: BLE001 - keep retrying on any error
                _LOGGER.debug("Reconnect to %s failed: %s", self.address, err)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, _RECONNECT_MAX_DELAY
                )

    async def stop(self) -> None:
        self._closing = True
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None

    async def _write(self, payload: bytes) -> None:
        try:
            await self._write_once(payload)
            return
        except (BleakError, RuntimeError, EOFError) as err:
            # If we never connected (or are shutting down), fail fast.
            if self._loop is None or self._closing:
                raise
            _LOGGER.debug(
                "Write to %s failed (%s); waiting for reconnect to retry",
                self.address,
                err,
            )
        if not await self._wait_connected(_WRITE_RETRY_WAIT):
            raise RuntimeError("Sauna not connected")
        await self._write_once(payload)

    async def _write_once(self, payload: bytes) -> None:
        if self._client is None or self._char is None or not self._client.is_connected:
            raise RuntimeError("Sauna not connected")
        async with self._lock:
            await self._client.write_gatt_char(self._char, payload, response=True)

    async def _wait_connected(self, timeout: float) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline and not self._closing:
            if self.is_connected:
                return True
            await asyncio.sleep(0.2)
        return self.is_connected

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
