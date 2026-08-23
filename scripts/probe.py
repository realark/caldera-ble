#!/usr/bin/env python3
"""Read-only BLE probe for the Relaxe Caldera 'Sauna-BLE' controller.

Connects, dumps the GATT table, subscribes to notifications, and decodes any
status frames it sees. It NEVER writes a command characteristic, so it cannot
change the sauna's state.
"""
import asyncio
import sys

from _common import resolve_device
from bleak import BleakClient

# Candidate serial-over-BLE UUIDs the OEM app uses (16-bit shorthand expands to
# the base 0000xxxx-0000-1000-8000-00805f9b34fb form that bleak reports).
NOTIFY_HINTS = {"fff1", "ffe1", "6e400003"}


def _hx(cs):
    return "0123456789abcdef".find(cs)


def decode_status(text: str) -> str | None:
    s = text.strip()
    if len(s) < 15 or s[0] != "x" or s[-1] != "z":
        return None
    try:
        power = "ON" if s[1] == "o" else "off" if s[1] == "f" else s[1]
        lamp = "ON" if s[2] == "o" else "off" if s[2] == "f" else s[2]
        if s[3] == "o":
            color = "on"
        elif s[3] == "f":
            color = "off"
        else:
            color = f"color#{s[3]}"
        audio = {"1": "bluetooth", "2": "usb"}.get(s[4], "none")
        unit = "C" if s[6] == "1" else "F" if s[6] == "0" else "?"
        cur = _hx(s[7]) * 16 + _hx(s[8])
        mins = _hx(s[9]) * 16 + _hx(s[10])
        tgt = _hx(s[11]) * 16 + _hx(s[12])
        err = s[13]
        return (
            f"power={power} lamp={lamp} color={color} audio={audio} "
            f"unit=°{unit} cur={cur}° target={tgt}° timer={mins}min err={err} "
            f"[reserved s5={s[5]!r}]"
        )
    except Exception as e:  # noqa: BLE001
        return f"<decode error: {e}>"


def on_notify(_char, data: bytearray):
    raw = bytes(data)
    txt = raw.decode("ascii", "replace")
    print(f"  NOTIFY  raw={raw.hex(' ')}  ascii={txt!r}")
    dec = decode_status(txt)
    if dec:
        print(f"          DECODED: {dec}")


async def main():
    addr = sys.argv[1] if len(sys.argv) > 1 else None
    print("Scanning for sauna ...")
    dev = await resolve_device(addr)
    if dev is None:
        print(
            "Not found. Set CALDERA_SAUNA_ADDRESS in .env, or check the phone "
            "isn't still connected to the sauna."
        )
        return
    print(f"Found {dev.name} @ {dev.address}. Connecting (read-only)...")
    async with BleakClient(dev) as client:
        print(f"Connected: {client.is_connected}\n=== GATT TABLE ===")
        notify_char = None
        for svc in client.services:
            print(f"[service] {svc.uuid}")
            for ch in svc.characteristics:
                props = ",".join(ch.properties)
                print(f"    [char] {ch.uuid}  ({props})")
                short = ch.uuid.split("-")[0][-4:].lower()
                full = ch.uuid.split("-")[0].lower()
                if ("notify" in ch.properties or "indicate" in ch.properties) and (
                    short in NOTIFY_HINTS or full in NOTIFY_HINTS or notify_char is None
                ):
                    notify_char = ch
        if notify_char is None:
            print("No notify characteristic found.")
            return
        print(f"\nSubscribing to {notify_char.uuid} for 30s (no writes)...")
        await client.start_notify(notify_char, on_notify)
        await asyncio.sleep(30)
        await client.stop_notify(notify_char)
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
