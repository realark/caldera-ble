# caldera-sauna

Local control library for **Relaxe Caldera** infrared saunas over Bluetooth LE,
plus (planned) a Home Assistant custom integration. Reverse-engineered from the
manufacturer Android app — see [`PROTOCOL.md`](PROTOCOL.md) for the full wire
protocol.

The sauna exposes a cheap serial-over-BLE module (service `FFF0`, characteristic
`FFF1` for both commands and status notifications) speaking a plain ASCII
protocol. No pairing/PIN/auth.

## Layout

```
src/caldera_sauna/
  protocol.py   pure codec (no I/O) — encode commands, decode status frames
  device.py     bleak + bleak-retry-connector transport (proxy-compatible)
  monitor.py    read-only CLI: scan, connect, print decoded state
scripts/probe.py  throwaway GATT dump / notify probe (read-only)
tests/            unit tests for the codec (no hardware needed)
```

## Dev quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest          # 23 tests, no hardware
ruff check src tests scripts
```

## Device config

Device-specific info stays out of git. Copy the example and fill in your
sauna's BLE address (find it with `bluetoothctl scan on` or nRF Connect):

```bash
cp .env.example .env
# edit .env -> CALDERA_SAUNA_ADDRESS=...
```

The `scripts/` tools read `.env`; if no address is set they scan for a device
whose name contains `CALDERA_SAUNA_NAME` (default `Sauna`).

## Read-only monitor (safe — sends no commands)

```bash
caldera-sauna-monitor                    # scan for a 'Sauna' device by name
caldera-sauna-monitor <BLE_ADDRESS>      # or target a specific address
```

> The module allows only one connection at a time. Disconnect the phone app
> before connecting from here.

## Status

- [x] Protocol reverse-engineered and documented
- [x] Codec + unit tests
- [x] BLE transport + read-only monitor, verified on real hardware
- [ ] Verified write commands (power/temp/timer/light) against hardware
- [ ] Home Assistant custom integration (climate + light + switch)
