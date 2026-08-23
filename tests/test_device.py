"""Tests for the BLE device layer (connect / notify / write / reconnect).

Uses fakes in place of bleak — no hardware. Async tests run via asyncio.run so
we don't need a pytest-asyncio dependency.
"""
import asyncio
from types import SimpleNamespace

from caldera_sauna import device
from caldera_sauna.device import CHAR_UUID, CalderaSauna

GOLDEN = b"xfff01000319e0z"


class FakeChar:
    def __init__(self, uuid: str) -> None:
        self.uuid = uuid


class FakeServices:
    def __init__(self, char: FakeChar) -> None:
        self._char = char

    def get_characteristic(self, uuid: str):
        return self._char if uuid == self._char.uuid else None


class FakeClient:
    def __init__(self, disconnected_callback=None) -> None:
        self.is_connected = True
        self._char = FakeChar(CHAR_UUID)
        self.services = FakeServices(self._char)
        self.writes: list[bytes] = []
        self._notify_cb = None
        self.disconnected_callback = disconnected_callback

    async def start_notify(self, char, cb) -> None:
        self._notify_cb = cb

    async def write_gatt_char(self, char, payload, response=True) -> None:
        self.writes.append(bytes(payload))

    async def disconnect(self) -> None:
        self.is_connected = False

    # --- test helpers ---
    def push(self, data: bytes) -> None:
        self._notify_cb(self._char, bytearray(data))

    def drop(self) -> None:
        self.is_connected = False
        if self.disconnected_callback:
            self.disconnected_callback(self)


def _fake_establish(clients: list[FakeClient]):
    async def establish(
        client_class, ble_device, name, disconnected_callback=None,
        ble_device_callback=None, **kw,
    ):
        client = FakeClient(disconnected_callback)
        clients.append(client)
        return client

    return establish


def _fake_device():
    return SimpleNamespace(name="Sauna-BLE", address="AA:BB:CC:DD:EE:FF")


def test_start_subscribes_and_decodes(monkeypatch):
    clients: list[FakeClient] = []
    monkeypatch.setattr(device, "establish_connection", _fake_establish(clients))

    async def go():
        states = []
        conns = []
        s = CalderaSauna(
            _fake_device(),
            state_callback=states.append,
            connection_callback=conns.append,
        )
        await s.start()
        assert conns == [True]
        clients[0].push(GOLDEN)
        assert s.state is not None and s.state.target_temp == 158
        assert states[-1].target_temp == 158
        await s.stop()

    asyncio.run(go())


def test_write_requires_connection(monkeypatch):
    clients: list[FakeClient] = []
    monkeypatch.setattr(device, "establish_connection", _fake_establish(clients))

    async def go():
        s = CalderaSauna(_fake_device())
        # not started yet -> should raise
        raised = False
        try:
            await s.async_set_power(True)
        except RuntimeError:
            raised = True
        assert raised

        await s.start()
        await s.async_set_lamp(True)
        assert clients[0].writes == [b"XL1ONZ\r\n"]
        await s.stop()

    asyncio.run(go())


def test_auto_reconnect_on_drop(monkeypatch):
    monkeypatch.setattr(device, "_RECONNECT_MIN_DELAY", 0.01)
    clients: list[FakeClient] = []
    monkeypatch.setattr(device, "establish_connection", _fake_establish(clients))

    async def go():
        conns = []
        s = CalderaSauna(_fake_device(), connection_callback=conns.append)
        await s.start()
        assert len(clients) == 1

        clients[0].drop()
        assert conns[-1] is False  # disconnect reported immediately

        await asyncio.sleep(0.1)  # let the reconnect loop run
        assert len(clients) == 2  # reconnected with a new client
        assert conns[-1] is True

        # a freshly reconnected client can still receive + write
        clients[1].push(GOLDEN)
        assert s.state is not None
        await s.stop()

    asyncio.run(go())


def test_stop_prevents_reconnect(monkeypatch):
    monkeypatch.setattr(device, "_RECONNECT_MIN_DELAY", 0.01)
    clients: list[FakeClient] = []
    monkeypatch.setattr(device, "establish_connection", _fake_establish(clients))

    async def go():
        s = CalderaSauna(_fake_device())
        await s.start()
        await s.stop()
        clients[0].drop()  # drop after stop
        await asyncio.sleep(0.1)
        assert len(clients) == 1  # no reconnect attempted

    asyncio.run(go())
