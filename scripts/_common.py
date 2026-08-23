"""Shared helpers for the dev scripts: load device info from .env and resolve
the BLE device.

Device-specific info (your sauna's BLE address) lives in a gitignored ``.env``
file, never in committed code. See ``.env.example``.
"""
from __future__ import annotations

import os

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from dotenv import load_dotenv

load_dotenv()  # populate os.environ from ./.env if present


def env_address() -> str | None:
    return os.environ.get("CALDERA_SAUNA_ADDRESS") or None


def env_name() -> str:
    return os.environ.get("CALDERA_SAUNA_NAME", "Sauna")


async def resolve_device(
    address: str | None = None, timeout: float = 15.0
) -> BLEDevice | None:
    """Find the sauna by explicit address, else CALDERA_SAUNA_ADDRESS, else by
    scanning for a device whose name contains CALDERA_SAUNA_NAME."""
    addr = address or env_address()
    if addr:
        return await BleakScanner.find_device_by_address(addr, timeout=timeout)
    name = env_name()
    return await BleakScanner.find_device_by_filter(
        lambda d, _ad: bool(d.name and name.lower() in d.name.lower()),
        timeout=timeout,
    )
