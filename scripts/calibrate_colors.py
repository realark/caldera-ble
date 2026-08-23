#!/usr/bin/env python3
"""Interactive color calibration: map each preset index to what it REALLY shows.

Walks indices 0..7, sending XCL0<n>Z and pausing so you can look at the sauna's
mood light and type what you see. Prints a ready-to-paste EFFECTS mapping at the
end. Run this NEXT TO the sauna, with the phone app disconnected.

    python scripts/calibrate_colors.py
"""
from __future__ import annotations

import asyncio

from _common import resolve_device

from caldera_sauna.device import CalderaSauna
from caldera_sauna.protocol import Color

# Nominal (app) labels, shown only as a hint — expect them to be wrong.
NOMINAL = {c.value: c.name.title() for c in Color}
SETTLE_S = 1.5


async def _ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip()


async def main() -> int:
    print("Finding sauna ...")
    dev = await resolve_device()
    if dev is None:
        print("Not found. Disconnect the phone app and check .env / power.")
        return 1

    sauna = CalderaSauna(dev)
    await sauna.start()
    print(f"Connected to {sauna.name}. Turning the mood light on...\n")
    await sauna.async_set_color_light(True)
    await asyncio.sleep(SETTLE_S)

    observed: dict[int, str] = {}
    n = 0
    while n < 8:
        await sauna.async_set_color(n)
        await asyncio.sleep(SETTLE_S)
        ans = await _ask(
            f"[index {n}] (app calls it '{NOMINAL[n]}')  "
            f"What do you actually see?  "
            f"[Enter=accept, r=repeat, b=back, q=quit] : "
        )
        low = ans.lower()
        if low == "r":
            continue
        if low == "b":
            n = max(0, n - 1)
            continue
        if low == "q":
            break
        observed[n] = ans or NOMINAL[n]
        n += 1

    await sauna.stop()

    print("\n===== observed mapping =====")
    for i in range(8):
        print(f"  {i}: {observed.get(i, '(skipped)')}")

    print("\n----- paste-ready EFFECTS for light.py -----")
    print("EFFECTS: dict[str, Color] = {")
    for i in range(8):
        label = observed.get(i)
        if label:
            safe = label.replace('"', "'").title()
            print(f'    "{safe}": Color({i}),')
    print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
