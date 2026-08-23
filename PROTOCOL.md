# Relaxe Caldera IR Sauna — Bluetooth Protocol

Reverse-engineered from the manufacturer Android app `cn.bestcontroller.sauna`
("infrared sauna.apk"). The app is a lightly-modified copy of Google's classic
*BluetoothChat* sample and supports **two transports carrying the identical
payload**:

- **Bluetooth Classic (RFCOMM / SPP)** — SPP UUID `00001101-0000-1000-8000-00805F9B34FB`.
- **Bluetooth LE (GATT, "BLE-UART" module)** — see UUIDs below.

Which one a given sauna uses depends purely on the radio in its controller
module. The app decides via `BluetoothDevice.getType()` (CLASSIC → SPP,
LE/DUAL → BLE). **The wire protocol (the ASCII frames) is the same either way.**

## BLE GATT layout

### Confirmed on real hardware (Relaxe Caldera, 2026-08-22)

- Advertised name: **`Sauna-BLE`** (LE), at a device-specific BLE address (kept
  out of the repo; set `CALDERA_SAUNA_ADDRESS` in `.env`). Because the name
  contains `Sauna` but not the uppercase `SAUNA`, the app selects the FFF0/FFF1
  UUID set and treats it as model 0 (30–70 °C).
- GATT table read from the device:

  ```
  service 0000fff0-0000-1000-8000-00805f9b34fb
      char 0000fff2-…  (read, notify)          # unused by app
      char 0000fff1-…  (write, notify)         # <-- commands AND status
      char 0000fff3-…  (write)                 # unused by app
  ```

- **`0000fff1`** is the single combined channel: **write** commands to it,
  **subscribe (notify)** to it for status frames. The property is plain `write`
  (with response), not write-without-response.
- Status frames arrive as unsolicited notifications on FFF1 roughly once per
  second, e.g. `xfff01000319e0z`.

### General (from the app, for other units)

The app's `SpBLE` class hardcodes a Nordic-UART default, but overwrites it at
connect time based on the advertised device name. The real modules are cheap
serial-over-BLE bridges:

| Device name contains | Service | Write (TX) char | Notify (RX) char |
| -------------------- | ------- | --------------- | ---------------- |
| `SAUNA`              | `0000FFE0-…` | `0000FFE1-…` | `0000FFE1-…` (same char) |
| `Sauna` / `GHS` / `Sweaty` | `0000FFF0-…` | `0000FFF1-…` | `0000FFF1-…` (same char, **confirmed**) |
| *(hardcoded default, likely unused)* | `6E400001-…` (Nordic UART) | `6E400002-…` | `6E400003-…` |

- Full UUID form: `0000FFF0-0000-1000-8000-00805F9B34FB` etc.
- Notifications enabled by writing the standard CCCD `00002902-…`.
- BLE scan name filter: name contains one of `Sweaty`, `GHS`, `Sauna`, `SAUNA`.
- The module appears to allow only one connection at a time / stops advertising
  while connected — disconnect the phone app before connecting from elsewhere.

## Framing

- **App → sauna (commands):** 6-byte ASCII, framed `X … Z`, then `\r\n`.
  Encoded as GBK (pure ASCII, so identical to ASCII/UTF-8).
- **Sauna → app (status):** ASCII, framed lowercase `x … z`, length ≥ 15.
  Note the case difference: commands use uppercase `X…Z`, status uses lowercase
  `x…z`.

## Commands (App → Sauna)

All are sent as the literal string + `\r\n`.

| Function         | TX string          | Notes                                                       |
|------------------|--------------------|-------------------------------------------------------------|
| Power ON         | `XSWONZ`           |                                                             |
| Power OFF        | `XSWOFZ`           |                                                             |
| Lamp ON          | `XL1ONZ`           | reading lamp / cabin light                                  |
| Lamp OFF         | `XL1OFZ`           |                                                             |
| Color light ON   | `XCLONZ`           | RGB mood light on                                           |
| Color light OFF  | `XCLOFZ`           |                                                             |
| Set color        | `XCL0` + `n` + `Z` | `n` = `0`–`7`, e.g. `XCL03Z`                                |
| Set target temp  | `XT1` + `HH` + `Z` | `HH` = target as 2 uppercase hex digits, e.g. 45 → `XT12DZ` |
| Set timer        | `XTM` + `HH` + `Z` | `HH` = minutes as 2 hex digits, e.g. 30 → `XTM1EZ`          |
| Unit °C → °F     | `XCTOFZ`           |                                                             |
| Unit °F → °C     | `XFTOCZ`           |                                                             |
| Music: Bluetooth | `XMU01Z`           | selects onboard BT audio input                              |
| Music: USB       | `XMU02Z`           | selects USB audio input                                     |
| Music: off       | `XMUOFZ`           |                                                             |
| Volume +         | `XVLICZ`           | only meaningful while BT/USB audio active                   |
| Volume −         | `XVLDCZ`           |                                                             |
| Track next       | `XCHICZ`           |                                                             |
| Track prev       | `XCHDCZ`           |                                                             |

Color index `n` — **nominal app labels** (0 White, 1 Purple, 2 Blue, 3 Cyan,
4 Green, 5 Yellow, 6 Changing, 7 Gradually) are wrong. **Actual colors observed
on hardware:**

| index | real color       |
|-------|------------------|
| 0     | White            |
| 1     | Yellow           |
| 2     | Green            |
| 3     | Cyan             |
| 4     | Blue             |
| 5     | Purple           |
| 6     | Red              |
| 7     | Changing (cycle) |
| 8     | Gradually (fade) |

> **Known quirk (confirmed on hardware):** the *actual* color the module lights
> up for a given index does not match these nominal labels. The OEM app shows
> the same wrong labels, so this is a module/firmware mismatch, not a decode
> error — we can't do better at the protocol level. In the HA integration we can
> relabel the effect names to whatever each index physically produces on a given
> unit.
>
> **Hidden preset (confirmed on hardware):** although the app only cycles 0–7,
> the command is a single digit and the firmware also responds to **index 8**
> (a 9th preset the app never exposes). **Index 9 is a no-op** (keeps the current
> color). So the usable range is **0–8**; senders should reject 9.

**Temp/timer encoding:** the value is emitted as its raw hex, *not* BCD:
`chars = HEX[v/16], HEX[v%16]`. So decimal 45 → `2D`, decimal 158 (°F) → `9E`.
The receiver decodes the two hex chars back to an integer the same way.

## Status frame (Sauna → App)

Parsed by `MainActivity.updateMainpage`. Validity check:
`len ≥ 15 && s[0]=='x' && s[last]=='z'`. Fixed offsets:

| Index | Field | Meaning |
| ----- | ----- | ------- |
| 0 | start | `'x'` |
| 1 | power | `'o'` = on, `'f'` = off |
| 2 | lamp | `'o'` = on, `'f'` = off |
| 3 | color light | `'o'` = on, `'f'` = off, or digit `'0'`–`'9'` = active color index (implies on) |
| 4 | audio source | `'1'` = Bluetooth, `'2'` = USB, else none |
| 5 | *reserved* | not read by the app |
| 6 | temp unit | `'1'` = °C, `'0'` = °F (only interpreted while power on) |
| 7–8 | current temp | 2 hex chars → int |
| 9–10 | set timer (min) | 2 hex chars → int |
| 11–12 | target temp | 2 hex chars → int |
| 13 | error code | single decimal digit (`0` = OK) |
| last | end | `'z'` |

A canonical frame is exactly 15 chars: `x` + 6 flag/unit chars + 6 hex chars +
1 error digit + `z`. The app tolerates longer frames (only checks the last char
is `z`).

## Temperature / timer limits (by model)

Model is inferred from the device name:

| model | name contains | °C range | °F range |
| ----- | ------------- | -------- | -------- |
| 0 | `BTSauna` (default) | 30–70 | 86–158 |
| 1 | `SAUNA` | 30–70 | 86–158 |
| 2 | `GHS-Sauna` | 30–75 | 86–167 |
| 3 | `Sauna-A1-` | 18–65 | 64–149 |

Timer range: 5–60 minutes (all models).

## Notes / gotchas

- Variable naming in the app is inverted: `poweroff == true` actually means
  power is **on**. Don't trust the names, trust the frames.
- There is no checksum, counter, or authentication anywhere. No PIN/pairing
  beyond standard BT. Commands are fire-and-forget; state is confirmed only via
  the next status frame.
- The app polls RSSI on a timer (BLE only) but never actively polls state — it
  relies on the sauna pushing status frames via notify / the serial stream.
- Everything is transport-agnostic: implement the ASCII codec once, then plug in
  either a BLE (NUS/FFE/FFF) or RFCOMM transport.
