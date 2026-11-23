# Galactic — notes for Claude

MicroPython platform for a Pimoroni Galactic Unicorn (53×11 LEDs): a launcher with shared
services plus apps (`app_<name>.py`). The clock is the first app, but the owner wants the
board used for more than a clock. The owner's board is the **Pico W (RP2040)** version;
code must also keep working on Pico 2 W (RP2350). Owner is in US Eastern time.

## Pushing = deploying

The board polls `device/manifest.json` on this repo's `main` branch every
`UPDATE_MINUTES` (config.py) and installs changed files by itself. **Anything pushed to
`main` reaches the physical clock within ~10–15 minutes** (raw.githubusercontent.com
caches for up to 5 minutes). There is no staging step.

Release steps, every time:

1. Edit files in `device/`.
2. `python3 tools/build_manifest.py` (regenerates fingerprints + version id).
3. `tools/check.sh` (full) — compile for both chips, lint, tests, simulated run.
   Look at the rendered stills/video when the change is visual.
4. Commit, then push to `main`. The pre-push hook re-runs `tools/check.sh --fast`;
   enable it in a fresh clone with `git config core.hooksPath .githooks`.

After a successful update the display shows a green light sweeping along the bottom row
twice. The owner can confirm it from that.

## Files

| File | Notes |
|---|---|
| `device/main.py`, `device/ota.py` | **Core.** Start-up, updates, rollback, recovery. Must stay self-contained (no imports from launcher/apps). A broken core file can only be fixed by hand over USB, so change them rarely and test with `tools/test_ota.py`. |
| `device/launcher.py` | Main loop + shared services: Wi-Fi jobs (NTP, update checks), system buttons (LUX, Zzz tap = sleep, Zzz hold = next app), `Store` settings, bottom-row system overlays, app crash isolation (non-clock app crash → fall back to clock), health → `mark_good()` after 60 s. The app interface is documented at the top. |
| `device/app_clock.py` | Clock app (buttons A–D themes, VOL± options) |
| `device/clockface.py` | Clock rendering: fonts, themes, compositing. Hot loops use `@micropython.native` |
| `device/timekeeping.py` | RTC holds UTC; local time + DST computed per frame |
| `device/net.py` | Non-blocking Wi-Fi connection manager |
| `device/config.py` | Owner's preferences, `APPS` list. **Deployed by OTA**, so it is the source of truth for time zone etc. App-specific keys are prefixed (`CLOCK_…`). |
| `device/secrets.py` | Wi-Fi password. Only on the board, never in git, never touched by OTA |
| `tools/mock/` | Fake `galactic`, `picographics`, `machine`, `network`, `ntptime`, `requests` for desktop runs |

## Safety net on the board

- Every downloaded file is checked against its SHA-256 in the manifest before anything is replaced.
- If the new version crashes before running cleanly for 60 s, or the board restarts 3 times
  without reaching that point, the previous files are restored. That version id is then
  never installed again. Publish a new version (any change gives a new id) to retry.
- If the launcher or clock crashes without a pending update, `ota.recover()` shows a pulsing
  red bar and checks for a fix every minute. Other apps crashing fall back to the clock.
- OTA delivers flat files only (no folders) with extensions `.py .json .txt .bin .jpg .png`
  (keep `EXTENSIONS` in `ota.py` and `tools/build_manifest.py` in sync).

## Adding an app

1. `device/app_<name>.py` with `class App` (`__init__(ctx)`, `frame(now, t)`, optional
   `start`, `button`, `quiet`). Store settings under `"<name>.<key>"` via `ctx.store`.
2. Add it to `APPS` in `device/config.py` (the first entry is the default).
3. Test it in the simulator: add a scenario to `tools/simulate.py` or a test like
   `tools/test_launcher.py`, and look at the rendered frames.
4. Mind RP2040 memory: only one app is instantiated at a time, but imported modules stay loaded.

## Constraints

- RP2040: no FPU, ~170 KB heap. Avoid per-pixel float work where integer maths will do;
  call `gc.collect()` before TLS.
- MicroPython differences: `hashlib` has no `hexdigest()` (use `binascii.hexlify`), no
  `str.format` alignment specs beyond basics, `@micropython.native` is a compile-time
  decorator, and no `__slots__`.
- Network calls block the display loop; keep them short and away from the minute rollover.
- The owner can't send logs remotely. Ask them to describe what the display shows. For
  details they can connect Thonny and read the Shell.
