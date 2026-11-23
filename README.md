# Galactic

Software for the Pimoroni **Galactic Unicorn (53×11 LEDs)**, either the Pico W or Pico 2 W
version. It is a small platform: a launcher that provides Wi-Fi, accurate local time,
brightness, sleep, saved settings and **automatic updates from this repository**, plus apps
that run on top of it.

The first app is a **clock** designed to sit in a video-call backdrop: large anti-aliased
digits that roll when they change, calm animated backgrounds, and brightness you can tune for a
webcam.

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
- A **2.4 GHz** Wi-Fi network (the Pico can't use 5 GHz-only networks). Wi-Fi is used to fetch
  the correct time and updates.

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

### 3 · Add your Wi-Fi details

All of the files that go on the board are in the [`device/`](device/) folder. Download the
repository (green **Code** button → **Download ZIP**) and unzip it.

Make a copy of `device/secrets.example.py` and name the copy **`secrets.py`**. Open it and enter
your Wi-Fi name and password. This file stays on your computer and the board; it is never
uploaded to GitHub.

Everything else (time zone, apps, defaults) is in `device/config.py`, which arrives with
updates, so change it in this repository rather than on the board.

### 4 · Copy the files to the board

1. In Thonny, open **View → Files**. The top pane is your computer; the bottom pane is the board.
2. In the top pane, browse to the `device` folder.
3. Select **every `.py` file** in the folder **except `secrets.example.py`** (Ctrl/Cmd-click):
   `app_clock.py`, `clockface.py`, `config.py`, `launcher.py`, `main.py`,
   `net.py`, `ota.py`, `secrets.py`, `timekeeping.py`.
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

**System (same in every app)**

| Button | Action |
|---|---|
| **LUX + / LUX −** (hold) | Brightness. A level bar shows along the bottom |
| **Zzz** tap | Display off / on (any button also wakes it) |
| **Zzz** hold (¾ s) | Next app. Dots along the bottom show which one (needs more than one app in `APPS`) |

**Clock app**

| Button | Action |
|---|---|
| **A / B / C / D** | Theme: Aurora / Sky / Amber / Prism |
| **Volume +** | 12-hour ⇄ 24-hour |
| **Volume −** | Seconds: thin progress bar → small digits → hidden |

Button changes are remembered across power cycles. If an update changes the same setting in
`config.py`, the new value replaces the remembered one.

## Tips for video calls

- **Brightness:** LEDs overwhelm webcams. Start at `0.2`–`0.35`, look at your own camera preview,
  and adjust with LUX ± until the digits look crisp, not like glowing blobs.
- **Amber** is the least distracting theme on camera. **Aurora** and **Sky** move slowly, so they
  look alive without pulling attention.
- If the background looks washed out on camera while the digits look right, lower
  `CLOCK_BACKGROUND_LEVEL` in `config.py` (e.g. `0.6`).
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
| Time is off by whole hours | `UTC_OFFSET_HOURS` in `config.py` should be your **winter** offset; `DST_RULE` handles summer. |
| Nothing at all | Press **Zzz** (the display may be switched off), or raise brightness with LUX +. |
| A green light sweeps along the bottom twice | An update was just installed. |
| A short **red** bar pulsing at the bottom, nothing else | The launcher or clock crashed. The board checks for a fixed version every minute and installs it on its own. (If any *other* app crashes, the board switches to the clock instead.) |

To see what the clock is doing, connect with Thonny and click **Stop**, then **Run**
(`main.py` open) — progress messages appear in the Shell.

**Optional, command line instead of Thonny:**

```bash
pip install mpremote
```

```bash
cd device && mpremote cp app_clock.py clockface.py config.py launcher.py main.py net.py ota.py secrets.py timekeeping.py : + reset
```

---

## Sending messages to the display

The board listens for messages on [ntfy](https://ntfy.sh), a free notification relay.
Anything that can make a web request can send one, and it appears within a second or two.

1. Pick a private **topic** (a long random name; it works like a password) and add it to
   `secrets.py` on the board: `NTFY_TOPIC = "your-topic-name"`.
2. Send:

```bash
curl -d "Lunch is here" https://ntfy.sh/your-topic-name
```

```bash
curl -H "Title: Build" -H "Priority: high" -d "Deploy finished" https://ntfy.sh/your-topic-name
```

Or install the **ntfy** phone app, subscribe to the same topic, and send from there. Power
Automate, Zapier, Home Assistant, GitHub Actions and similar tools can all call that URL.

| Priority (`Priority:` header) | On the display |
|---|---|
| `min` / `low` (1–2) | 4 seconds, dimmer |
| `default` (3) | 6 seconds |
| `high` (4) | 10 seconds, amber |
| `urgent` (5) | 15 seconds, red. Goes ahead of other messages and wakes a sleeping display |

A tag naming a colour (`Tags: green`; also red, orange, amber, yellow, cyan, blue, purple,
pink, white) sets the text colour. Text with a title shows as "Title: message". Long messages
scroll. Emoji and other non-ASCII characters show as `?`; curly quotes and dashes are converted.

**Privacy:** messages pass through the public ntfy.sh server, and anyone who knows the topic
can send to your display. For more control, ntfy can be self-hosted (it ships as a Docker
image); point `NTFY_SERVER` in `config.py` at it (plain `http://` works on a local network).

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

Updates can add, change or remove apps as well as the system itself. `secrets.py` (your Wi-Fi
password) and the button-press settings are never touched by updates.
Updates use only the Wi-Fi; the computer the board is plugged into doesn't matter.

**Security note:** MicroPython's HTTPS library doesn't verify server certificates. Someone who
controls your Wi-Fi network or the connection to GitHub could in principle feed the clock
different code. That code could only affect the clock itself, but treat the board like any
other unattended network gadget. Anyone with write access to the repository can also change
what the clock runs.

## How it works

| File | Role |
|---|---|
| `device/main.py` | Start-up: runs the updater's safety checks, then the launcher; crash handling |
| `device/ota.py` | Automatic updates: download, verify, install, roll back, recovery mode |
| `device/launcher.py` | Runs apps (~30 fps) and shared services: Wi-Fi, time, updates, brightness, sleep, settings, crash isolation |
| `device/app_clock.py` | The clock app |
| `device/clockface.py` | Clock rendering: fonts, themes, roll animation, per-pixel compositing |
| `device/text.py` | Proportional pixel font and text drawing, used by messages and apps |
| `device/inbox.py` | Listens for ntfy messages over one streaming connection, read without blocking |
| `device/timekeeping.py` | Local time and daylight-saving maths, NTP time sync |
| `device/net.py` | Keeps Wi-Fi connected, reconnecting with back-off |
| `device/config.py` | Your preferences |
| `device/manifest.json` | Generated: what the board should have (`tools/build_manifest.py`) |
| `tools/check.sh` | Every check that must pass before a release; also run by GitHub Actions and the pre-push hook |
| `tools/simulate.py` | Runs the real device code on a PC against mock hardware and renders preview video/images |
| `tools/test_ota.py` | Updater tests against a fake GitHub, including broken releases and rollback |
| `tools/test_launcher.py` | App switching, sleep, crash isolation, saved settings, messages |
| `tools/test_inbox.py` | ntfy stream parsing, reconnects, de-duplication, priorities |
| `tools/test_timekeeping.py` | Checks local-time maths against the IANA time-zone database (2025–2035) |

The board keeps UTC; local time is calculated each frame, so daylight-saving changes happen at the
right moment with no network needed.

### Writing an app

Create `device/app_<name>.py` with a class called `App`, then add `"<name>"` to `APPS` in
`config.py`:

```python
class App:
    def __init__(self, ctx):          # ctx.gfx, ctx.width, ctx.height, ctx.store,
        self.ctx = ctx                # ctx.local_time(now), ctx.net_status(), ctx.cfg(...)

    def frame(self, now, t):          # draw a whole frame into ctx.gfx (53 x 11)
        ...

    # optional
    def start(self, now): ...         # became visible
    def button(self, name, now): ...  # "A" "B" "C" "D" "VOL_UP" "VOL_DOWN"
    def quiet(self, now): ...         # False = don't pause for network now
```

The launcher calls `frame()` about 30 times a second, then updates the display. See
`device/launcher.py` for details.

**Text and messages.** `device/text.py` is a proportional pixel font covering printable ASCII
(7-row capitals, descenders on g j p q y). "Hello, world" is 47 px wide, so it fits the display.

```python
import text
text.draw(ctx.gfx, "Hi", x, y, (255, 200, 120))   # or a function x -> (r, g, b)
text.measure("Hi")                                # width in pixels

ctx.notify("Meeting in 5 minutes", seconds=5)     # full-screen message over any app
```

Messages slide in, show a shrinking countdown line, then slide out and hand back to the app.
Text too wide for the display scrolls instead. Messages queue if several arrive.
`ANNOUNCEMENT` in `config.py` shows a one-off message once after an update delivers a new one.

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
