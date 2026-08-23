#!/usr/bin/env python3
"""Send ONE command to the sauna and confirm it via the status frames.

Safety-first write tester:
  * captures a baseline status frame before sending,
  * sends exactly one command,
  * watches the next few frames and highlights what changed,
  * optionally reverts.

Defaults to LED-only actions (lamp / color light) — nothing that turns on the
heater. Requires an explicit command argument, so nothing fires by accident.

Examples:
    python scripts/send_one.py lamp-on
    python scripts/send_one.py lamp-off --revert
    python scripts/send_one.py color-on
    python scripts/send_one.py color 4          # set color preset (0..7)
    python scripts/send_one.py --list
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import sys

from _common import resolve_device

from caldera_sauna import protocol as p
from caldera_sauna.device import CalderaSauna
from caldera_sauna.protocol import SaunaState

# name -> (builds command bytes, human description). LED-only by default.
COMMANDS: dict[str, tuple] = {
    "lamp-on": (lambda a: p.cmd_lamp(True), "cabin lamp ON"),
    "lamp-off": (lambda a: p.cmd_lamp(False), "cabin lamp OFF"),
    "color-on": (lambda a: p.cmd_color_light(True), "RGB mood light ON"),
    "color-off": (lambda a: p.cmd_color_light(False), "RGB mood light OFF"),
    "color": (lambda a: p.cmd_set_color(int(a)), "set RGB color preset 0..7"),
    # Heating-related — present but you must opt in explicitly by name.
    "power-on": (lambda a: p.cmd_power(True), "POWER/HEATER ON (heats!)"),
    "power-off": (lambda a: p.cmd_power(False), "power/heater OFF"),
    "temp": (lambda a: p.cmd_set_target_temp(int(a)), "set target temp (raw value)"),
    "timer": (lambda a: p.cmd_set_timer(int(a)), "set timer minutes"),
}


def _diff(before: SaunaState | None, after: SaunaState | None) -> str:
    if before is None or after is None:
        return "(missing a snapshot)"
    b = dataclasses.asdict(before)
    a = dataclasses.asdict(after)
    changes = [
        f"{k}: {b[k]!r} -> {a[k]!r}" for k in a if k != "raw" and b[k] != a[k]
    ]
    return "\n    ".join(changes) if changes else "(no fields changed)"


async def _wait_for_frame(
    sauna: CalderaSauna, timeout: float = 6.0
) -> SaunaState | None:
    """Wait until at least one status frame has arrived."""
    for _ in range(int(timeout * 10)):
        if sauna.state is not None:
            return sauna.state
        await asyncio.sleep(0.1)
    return sauna.state


async def _run(cmd: str, arg: str | None, revert: bool) -> int:
    builder, desc = COMMANDS[cmd]
    try:
        payload = builder(arg)
    except (TypeError, ValueError) as e:
        print(f"Bad argument for '{cmd}': {e}")
        return 2

    print("Finding sauna ...")
    dev = await resolve_device()
    if dev is None:
        print(
            "Not found. Set CALDERA_SAUNA_ADDRESS in .env, or check the phone "
            "isn't still connected to the sauna."
        )
        return 1

    sauna = CalderaSauna(dev)
    await sauna.start()
    try:
        before = await _wait_for_frame(sauna)
        print(f"\nBEFORE: {before.raw if before else '(no frame yet)'}")

        print(f"\n>>> SENDING: {cmd} ({desc})  bytes={payload!r}")
        await sauna._write(payload)  # single, explicit write

        await asyncio.sleep(2.5)  # let a few status frames roll in
        after = sauna.state
        print(f"AFTER:  {after.raw if after else '(no frame)'}")
        print(f"\nCHANGED:\n    {_diff(before, after)}")

        if revert and cmd in ("lamp-on", "lamp-off", "color-on", "color-off"):
            opposite = {
                "lamp-on": "lamp-off",
                "lamp-off": "lamp-on",
                "color-on": "color-off",
                "color-off": "color-on",
            }[cmd]
            print(f"\n>>> REVERTING with {opposite} ...")
            await sauna._write(COMMANDS[opposite][0](None))
            await asyncio.sleep(2.0)
            print(f"REVERTED: {sauna.state.raw if sauna.state else '(no frame)'}")
    finally:
        await sauna.stop()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", nargs="?", help="one of --list")
    ap.add_argument("arg", nargs="?", help="argument for color/temp/timer")
    ap.add_argument("--revert", action="store_true", help="undo lamp/color after")
    ap.add_argument("--list", action="store_true", help="list commands and exit")
    args = ap.parse_args()

    if args.list or not args.command:
        print("Available commands:")
        for k, (_, d) in COMMANDS.items():
            print(f"  {k:12} {d}")
        sys.exit(0)
    if args.command not in COMMANDS:
        print(f"Unknown command '{args.command}'. Use --list.")
        sys.exit(2)
    sys.exit(asyncio.run(_run(args.command, args.arg, args.revert)))


if __name__ == "__main__":
    main()
