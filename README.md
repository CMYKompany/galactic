# Galactic Unicorn Clock

A clock for the Pimoroni **Galactic Unicorn (53×11 LEDs)** — either version, Pico W or Pico 2 W — designed to sit in a
video-call backdrop: large anti-aliased digits that roll when they change, calm animated
backgrounds, and brightness you can tune for a webcam.

![Aurora theme](docs/aurora.png)

| | |
|---|---|
| ![Sky, daytime](docs/sky-day.png) **B · Sky** follows the real sky — dawn, day, dusk, stars at night | ![Amber](docs/amber.png) **C · Amber** black background, glowing digits (calmest on camera) |
| ![Prism](docs/prism.png) **D · Prism** slowly drifting rainbow digits | ![Seconds as digits](docs/seconds-digits.png) Seconds shown as small digits |

A 44-second simulated run (boot, Wi-Fi sync, a minute rollover, every theme) is in
[`docs/preview.mp4`](docs/preview.mp4).

---

## What you need

- The Galactic Unicorn (Pico W or Pico 2 W version) and a **micro-USB cable that carries data** (some phone-charging cables
  are power-only — if no drive appears in step 1, try another cable).
- A Windows, Mac or Linux computer. **No Raspberry Pi and no Docker are needed** — the Pico 2 W
  soldered to the back of the Unicorn is the computer. Your PC is only used to copy files onto it.
- A **2.4 GHz** Wi-Fi network (the Pico can't use 5 GHz-only networks). Wi-Fi is used only to
  fetch the correct time.

## Setup (about 15 minutes, once)

### 1 · Put the latest Pimoroni firmware on the board

1. Download the newest firmware from
   **https://github.com/pimoroni/unicorn/releases/latest**. Under *Assets* there are two kinds
   of `.uf2` file; which one you need depends on the Pico on the back of your Unicorn:

   | Printed on the Pico | Drive name in step 3 | Firmware file starts with |
   |---|---|---|
   | **Pico W** (older Unicorns) | `RPI-RP2` | **`pico_w_galactic`** |
   | **Pico 2 W** | `RP2350` | **`pico2_w_galactic`** |

   If you copy the wrong one, nothing happens: the file just sits on the drive. Download the
   other one and try again. (The `-with-filesystem` versions also work; they just include
   Pimoroni's demos.)
2. Plug the Unicorn into your computer.
3. On the back of the Unicorn, **hold the BOOTSEL button** on the Pico, **tap RESET**, then let go
   of BOOTSEL. A USB drive called **RPI-RP2** or **RP2350** appears.
4. Drag the `.uf2` file onto that drive. Within a few seconds the drive disappears and the board
   restarts on its own.

### 2 · Install Thonny (a simple editor that talks to the board)

1. Download and install from **https://thonny.org**.
2. Open Thonny. With the Unicorn plugged in, click the text in the **bottom-right corner**
   (it starts out as *Local Python 3 • Thonny's Python*, meaning your PC) and choose
   **MicroPython (Raspberry Pi Pico)**. This is the right choice for both board versions.
3. The *Shell* panel at the bottom should show something like `MicroPython v1.2x … Pico W`
   (or `Pico 2 W`).
   If it doesn't, click the red **Stop** button in the toolbar.

   Still not connecting? Open **Tools → Options → Interpreter**, choose
   *MicroPython (Raspberry Pi Pico)*, and set **Port** to the *USB Serial Device (COMx)* entry.
   If no such entry exists, Windows can't see the board: try another USB cable (many are
   charge-only) or another USB port, or repeat step 1.

### 3 · Fill in your settings

All of the files that go on the board are in the [`device/`](device/) folder.

1. Make a copy of `device/secrets.example.py` and name the copy **`secrets.py`**. Open it and enter
   your Wi-Fi name and password.
2. Open `device/config.py` and set your time zone. The two lines that matter:
   ```python
   UTC_OFFSET_HOURS = -5   # your *winter* offset: Eastern -5, Central -6, Mountain -7, Pacific -8
   DST_RULE = "US"         # "US", "EU", "AU" or "NONE"
   ```
   Daylight saving is handled automatically; you never adjust the clock by hand.
   The other settings (theme, 12/24 hour, brightness) can be changed later with the buttons.

### 4 · Copy the files to the board

1. In Thonny, open **View → Files**. The top pane is your computer; the bottom pane is the board.
2. In the top pane, browse to the `device` folder.
3. Select **every `.py` file** in the folder **except `secrets.example.py`** (Ctrl/Cmd-click):
   `app.py`, `clockface.py`, `config.py`, `main.py`, `net.py`, `ota.py`, `secrets.py`,
   `timekeeping.py`.
4. Right-click → **Upload to /**. If it asks to overwrite files (for example Pimoroni's demo
   `main.py`, or an older version of the clock), say yes.

This is the last time you need to copy files by hand: from now on the clock
[updates itself](#automatic-updates).

### 5 · Start it

Click Thonny's red **Stop** button, or unplug the board and plug it back in (into any USB charger
from here on). You'll see dashes with a light sweeping underneath while it connects. After a few
seconds the time rolls in.

---

## Buttons

| Button | Action |
|---|---|
| **A / B / C / D** | Theme: Aurora / Sky / Amber / Prism |
| **Volume +** | 12-hour ⇄ 24-hour |
| **Volume −** | Seconds: thin progress bar → small digits → hidden |
| **LUX + / LUX −** (hold) | Brightness — a level bar shows along the bottom |
| **Zzz** | Display off / on (any button also wakes it) |

Button changes are remembered across power cycles. Editing `config.py` and re-uploading it
resets them to your new values.

## Tips for video calls

- **Brightness:** LEDs overwhelm webcams. Start at `0.2`–`0.35`, look at your own camera preview,
  and adjust with LUX ± until the digits look crisp, not like glowing blobs.
- **Amber** is the least distracting theme on camera. **Aurora** and **Sky** move slowly, so they
  look alive without pulling attention.
- If the background looks washed out on camera while the digits look right, lower
  `BACKGROUND_LEVEL` in `config.py` (e.g. `0.6`).
- On the older **Pico W** boards the background animation may be a little less smooth (no
  hardware floating point). If it looks choppy, set `FPS = 20` in `config.py`.
- If you see faint rolling bands across the display on video, nudge the brightness up or down a
  step. They come from the LED refresh beating against the camera's frame rate, and the banding
  depends on the brightness level.

## Troubleshooting

| What you see | Meaning / fix |
|---|---|
| Dashes with a light sweeping underneath | Connecting to Wi-Fi — normally a few seconds. |
| Dashes with a pulsing **red** mark underneath | Wi-Fi failed. Check `secrets.py` (exact name and password, case-sensitive) and that the network is 2.4 GHz. It keeps retrying on its own. |
| Time is off by whole hours | `UTC_OFFSET_HOURS` should be your **winter** offset; `DST_RULE` handles summer. |
| Nothing at all | Press **Zzz** (the display may be switched off), or raise brightness with LUX +. |
| A green light sweeps along the bottom twice | An update was just installed. |
| A short **red** bar pulsing at the bottom, no digits | The clock code crashed. The board checks for a fixed version every minute and installs it on its own. |

To see what the clock is doing, connect with Thonny and click **Stop**, then **Run**
(`main.py` open) — progress messages appear in the Shell.

**Optional, command line instead of Thonny:**

```bash
pip install mpremote
```

```bash
cd device && mpremote cp app.py clockface.py config.py main.py net.py ota.py secrets.py timekeeping.py : + reset
```

---

## Automatic updates

Once `UPDATE_REPO` in `config.py` names a GitHub repository, the clock checks it every
`UPDATE_MINUTES` (10 by default) and installs new versions by itself:

1. It downloads `device/manifest.json`: a version id and a SHA-256 fingerprint for every file
   that belongs on the board.
2. It downloads only the files whose fingerprint differs and checks each against the manifest.
   If anything doesn't match, nothing on the board changes.
3. It swaps the new files in, keeps the old ones as backups, and restarts. A green sweep along the
   bottom row means an update arrived.
4. If the new version crashes before it has run cleanly for a minute, or the board restarts three
   times without getting that far, the old files are restored automatically and that version is
   skipped.

`secrets.py` (your Wi-Fi password) and the button-press settings are never touched by updates.
Updates use only the Wi-Fi; the computer the board is plugged into doesn't matter.

**Security note:** MicroPython's HTTPS library doesn't verify server certificates. Someone who
controls your Wi-Fi network or the connection to GitHub could in principle feed the clock
different code. That code could only affect the clock itself, but treat the board like any
other unattended network gadget. Anyone with write access to the repository can also change
what the clock runs.

## How it works

| File | Role |
|---|---|
| `device/main.py` | Start-up: runs the updater's safety checks, then the clock; crash handling |
| `device/ota.py` | Automatic updates: download, verify, install, roll back, recovery mode |
| `device/app.py` | Main loop (~30 fps): buttons, saved settings, time sync and update checks |
| `device/clockface.py` | Fonts, themes, roll animation, per-pixel compositing (background → halo → digits → overlays) |
| `device/timekeeping.py` | Local time and daylight-saving maths, NTP time sync |
| `device/net.py` | Keeps Wi-Fi connected, reconnecting with back-off |
| `device/config.py` | Your preferences |
| `device/manifest.json` | Generated: what the board should have (`tools/build_manifest.py`) |
| `tools/check.sh` | Every check that must pass before a release; also run by GitHub Actions and the pre-push hook |
| `tools/simulate.py` | Runs the real device code on a PC against mock hardware and renders preview video/images |
| `tools/test_ota.py` | Updater tests against a fake GitHub, including broken releases and rollback |
| `tools/test_timekeeping.py` | Checks local-time maths against the IANA time-zone database (2025–2035) |

The board keeps UTC; local time is calculated each frame, so daylight-saving changes happen at the
right moment with no network needed.

### Developing

Pushing to `main` deploys to the clock. Before every push:

```bash
python3 tools/build_manifest.py
```

```bash
tools/check.sh
```

`check.sh` needs `pip install mpy-cross pillow pyflakes` and ffmpeg. To have git refuse a push
that fails the checks:

```bash
git config core.hooksPath .githooks
```
