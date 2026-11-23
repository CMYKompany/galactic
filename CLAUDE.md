# Galactic Unicorn Clock — notes for Claude

MicroPython clock for a Pimoroni Galactic Unicorn (53×11 LEDs). The owner's board is the
**Pico W (RP2040)** version; code must also keep working on Pico 2 W (RP2350).

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

After a successful update the clock shows a green light sweeping along the bottom row
twice. The owner can confirm it from that.

## Files

| File | Notes |
|---|---|
| `device/main.py`, `device/ota.py` | **Core.** Start-up, updates, rollback, recovery. Must stay self-contained (no imports from clock code). A broken core file can only be fixed by hand over USB, so change them rarely and test with `tools/test_ota.py`. |
| `device/app.py` | Main loop: buttons, settings, Wi-Fi jobs (NTP, update checks), health → `mark_good()` after 60 s |
| `device/clockface.py` | Fonts, themes, compositing. Hot loops use `@micropython.native` |
| `device/timekeeping.py` | RTC holds UTC; local time + DST computed per frame |
| `device/net.py` | Non-blocking Wi-Fi connection manager |
| `device/config.py` | Owner's preferences. **Deployed by OTA**, so it is the source of truth for time zone etc. |
| `device/secrets.py` | Wi-Fi password. Only on the board, never in git, never touched by OTA |
| `tools/mock/` | Fake `galactic`, `picographics`, `machine`, `network`, `ntptime`, `requests` for desktop runs |

## Safety net on the board

- Every downloaded file is checked against its SHA-256 in the manifest before anything is replaced.
- If the new version crashes before running cleanly for 60 s, or the board restarts 3 times
  without reaching that point, the previous files are restored. That version id is then
  never installed again. Publish a new version (any change gives a new id) to retry.
- If the clock crashes without a pending update, `ota.recover()` shows a pulsing red bar
  and checks for a fix every minute.

## Constraints

- RP2040: no FPU, ~170 KB heap. Avoid per-pixel float work where integer maths will do;
  call `gc.collect()` before TLS.
- MicroPython differences: `hashlib` has no `hexdigest()` (use `binascii.hexlify`), no
  `str.format` alignment specs beyond basics, `@micropython.native` is a compile-time
  decorator, and no `__slots__`.
- Network calls block the display loop; keep them short and away from the minute rollover.
- The owner can't send logs remotely. Ask them to describe what the display shows. For
  details they can connect Thonny and read the Shell.
