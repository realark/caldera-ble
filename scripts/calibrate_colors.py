#!/usr/bin/env python3
"""Interactive color calibration: map each preset index to what it REALLY shows.

Walks indices 0..9 (0..7 are what the app uses; 8..9 are a probe for hidden
presets the firmware may or may not support), sending XCL0<n>Z and pausing so
you can look at the sauna's mood light and type what you see. After each send it
also prints the index the DEVICE echoes back in its status frame (position 3),
which hints whether the value actually took. Prints a paste-ready mapping at the
end. Run NEXT TO the sauna, with the phone app AND the HA integration
disconnected (single connection only).

    python scripts/calibrate_colors.py
"""
from __future__ import annotations

import asyncio

from _common import resolve_device

from caldera_sauna.device import CalderaSauna
from caldera_sauna.protocol import Color, SaunaState

# Nominal (app) labels, shown only as a hint — expect them to be wrong.
NOMINAL = {c.value: c.name.title() for c in Color}
MAX_INDEX = 9
SETTLE_S = 1.8
UNUSED = "\x00unused"  # sentinel


async def _ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip()


async def main() -> int:
    print("Finding sauna ...")
    dev = await resolve_device()
    if dev is None:
        print("Not found. Disconnect the phone app / HA integration, check .env.")
        return 1

    latest: dict[str, SaunaState | None] = {"state": None}
    sauna = CalderaSauna(dev, state_callback=lambda s: latest.__setitem__("state", s))
    await sauna.start()
    print(f"Connected to {sauna.name}. Turning the mood light on...\n")
    await sauna.async_set_color_light(True)
    await asyncio.sleep(SETTLE_S)

    observed: dict[int, str] = {}
    n = 0
    while n <= MAX_INDEX:
        await sauna.async_set_color(n)
        await asyncio.sleep(SETTLE_S)
        state = latest["state"]
        echoed = state.raw[3] if state and len(state.raw) > 3 else "?"
        hint = f"app-label='{NOMINAL[n]}'" if n in NOMINAL else "beyond app range"
        tag = " (probe)" if n > 7 else ""
        ans = await _ask(
            f"[index {n}{tag}]  {hint}  device-echoes-index='{echoed}'\n"
            f"   what do you see?  [type color / u=unused / r=repeat / "
            f"b=back / q=quit] : "
        )
        low = ans.lower()
        if low == "r":
            continue
        if low == "b":
            observed.pop(n, None)
            n = max(0, n - 1)
            continue
        if low == "q":
            break
        if low in ("u", "unused", "none", "x"):
            observed[n] = UNUSED
        else:
            observed[n] = ans or NOMINAL.get(n, f"index{n}")
        n += 1

    await sauna.stop()

    print("\n===== observed mapping =====")
    for i in range(MAX_INDEX + 1):
        val = observed.get(i)
        shown = "(unused)" if val == UNUSED else (val or "(skipped)")
        print(f"  {i}: {shown}")

    used = {i: v for i, v in observed.items() if v not in (None, UNUSED)}
    print("\n----- paste-ready EFFECTS for light.py -----")
    print("EFFECTS: dict[str, Color] = {")
    for i in sorted(used):
        safe = used[i].replace('"', "'").title()
        print(f'    "{safe}": Color({i}),')
    print("}")
    unused = [i for i, v in observed.items() if v == UNUSED]
    if unused:
        print(f"# unused indices (do nothing): {unused}")
    highest = max(used) if used else -1
    if highest > 7:
        print(f"# NOTE: hidden preset(s) found beyond app range, up to index {highest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
