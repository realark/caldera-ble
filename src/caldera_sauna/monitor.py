"""Read-only monitor CLI: scan, connect, and print decoded sauna state.

Sends no commands — safe to leave running. Usage::

    caldera-sauna-monitor            # scan by name 'Sauna'
    caldera-sauna-monitor <ADDRESS>  # connect to a specific address
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib

from bleak import BleakScanner

from .device import CalderaSauna
from .protocol import SaunaState


def _print_state(st: SaunaState) -> None:
    if st.color is not None:
        color = st.color.name.title()
    else:
        color = "on" if st.color_on else "off"
    print(
        f"power={'ON' if st.power else 'off':3} "
        f"cur={st.current_temp:3}°{st.unit.name[0]} "
        f"target={st.target_temp:3}°{st.unit.name[0]} "
        f"timer={st.timer_minutes:2}min "
        f"lamp={'ON' if st.lamp else 'off':3} "
        f"color={color:9} audio={st.audio.name.lower():9} "
        f"err={st.error}  [{st.raw}]"
    )


async def _run(address: str | None, name: str, seconds: float) -> int:
    if address:
        dev = await BleakScanner.find_device_by_address(address, timeout=15.0)
    else:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, _ad: bool(d.name and name.lower() in d.name.lower()),
            timeout=15.0,
        )
    if dev is None:
        print("Sauna not found. Is the phone still connected to it?")
        return 1

    print(f"Connecting to {dev.name} @ {dev.address} (read-only)...")
    sauna = CalderaSauna(dev, state_callback=_print_state)
    await sauna.start()
    print(f"Subscribed. Printing state for {seconds:.0f}s (no commands sent)...")
    try:
        await asyncio.sleep(seconds)
    finally:
        await sauna.stop()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only Caldera sauna monitor")
    ap.add_argument("address", nargs="?", help="BLE address (else scan by name)")
    ap.add_argument("--name", default="Sauna", help="name substring to scan for")
    ap.add_argument("--seconds", type=float, default=60.0)
    args = ap.parse_args()
    rc = 1
    with contextlib.suppress(KeyboardInterrupt):
        rc = asyncio.run(_run(args.address, args.name, args.seconds))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
