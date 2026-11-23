"""Tests for the launcher (device/launcher.py): app switching, sleep, crash
isolation and saved settings, run through main.py on a temporary "board".

    python3 tools/test_launcher.py
"""
import contextlib
import datetime as dt
import io
import json
import os
import runpy
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = os.path.join(os.path.dirname(HERE), "device")
sys.path.insert(0, os.path.join(HERE, "mock"))

import galactic  # noqa: E402  (mock)
import requests  # noqa: E402  (mock)
from sim import SIM, SimDone, install_time  # noqa: E402

install_time()
sys.print_exception = lambda e: traceback.print_exception(e)
GU = galactic.GalacticUnicorn

RED_APP = b'''
class App:
    def __init__(self, ctx):
        self.gfx = ctx.gfx
    def frame(self, now, t):
        self.gfx.set_pen(self.gfx.create_pen(200, 0, 0))
        self.gfx.clear()
'''

CRASHY_APP = b'''
class App:
    def __init__(self, ctx):
        self.n = 0
    def frame(self, now, t):
        self.n += 1
        if self.n > 10:
            raise RuntimeError("crashy app")
'''

MODULES = ("main", "launcher", "app_clock", "app_red", "app_crashy", "ota", "net",
           "clockface", "timekeeping", "config", "secrets")


def make_board(apps, extra_config=""):
    board = tempfile.mkdtemp(prefix="board-")
    for name in os.listdir(DEVICE):
        if name.endswith(".py") and not name.startswith("secrets"):
            with open(os.path.join(DEVICE, name), "rb") as f:
                data = f.read()
            if name == "config.py":
                data += "\nAPPS = {!r}\nUPDATE_REPO = ''\n{}\n".format(apps, extra_config).encode()
            with open(os.path.join(board, name), "wb") as f:
                f.write(data)
    for name, data in (("app_red.py", RED_APP), ("app_crashy.py", CRASHY_APP)):
        with open(os.path.join(board, name), "wb") as f:
            f.write(data)
    with open(os.path.join(board, "secrets.py"), "w") as f:
        f.write('WIFI_SSID = "test"\nWIFI_PASSWORD = "pw"\n')
    return board


def boot(board, seconds, presses=()):
    """Run main.py; returns (outcome, stdout, frames {ms: buf}, final brightness)."""
    os.chdir(board)
    for m in MODULES:
        sys.modules.pop(m, None)
    sys.path[:] = [p for p in sys.path if not p.startswith(tempfile.gettempdir())]
    sys.path.insert(0, board)
    requests.serve(None)
    SIM.__init__()
    SIM.true_utc0 = dt.datetime(2026, 11, 23, 15, 0, 20, tzinfo=dt.timezone.utc).timestamp()
    SIM.stop_ms = int(seconds * 1000)
    SIM.presses = [(int(a * 1000), int((a + d) * 1000), s) for a, d, s in presses]
    frames = {}
    bright = [None]

    def on_frame(sim, buf, brightness):
        frames[sim.ms] = [row[:] for row in buf]
        bright[0] = brightness

    SIM.on_frame = on_frame
    out = io.StringIO()
    outcome = "exited"
    with contextlib.redirect_stdout(out):
        try:
            runpy.run_path(os.path.join(board, "main.py"), run_name="__main__")
        except SimDone as e:
            outcome = "reset" if "reset" in str(e) else "running"
    return outcome, out.getvalue(), frames, bright[0]


def frame_at(frames, sec):
    ms = min((m for m in frames if m >= sec * 1000), default=max(frames))
    return frames[ms]


def is_solid(buf, color):
    return all(px == color for row in buf for px in row)


def settings(board):
    with open(os.path.join(board, "settings.json")) as f:
        return json.load(f)


# ------------------------------------------------------------------ tests

def test_hold_zzz_switches_app_and_remembers_it():
    board = make_board(("clock", "red"))
    outcome, log, frames, _ = boot(board, 12, presses=[(3, 1.0, GU.SWITCH_SLEEP)])
    assert outcome == "running", log
    assert "Starting app: clock" in log and "Starting app: red" in log, log
    assert not is_solid(frame_at(frames, 2), (200, 0, 0))
    # bottom row shows the app dots briefly; rows above are the red app
    buf = frame_at(frames, 4.2)
    assert all(px == (200, 0, 0) for row in buf[:-1] for px in row)
    assert is_solid(frame_at(frames, 8), (200, 0, 0))
    assert settings(board)["system.app"][0] == "red"
    # restart: comes back in the red app
    _, log, frames, _ = boot(board, 3)
    assert "Starting app: red" in log and "Starting app: clock" not in log, log
    print("ok  holding Zzz switches app; choice survives a restart")


def test_tap_zzz_sleeps_and_any_button_wakes():
    board = make_board(("red",))
    _, log, frames, _ = boot(board, 8, presses=[(2, 0.1, GU.SWITCH_SLEEP),
                                                (5, 0.1, GU.SWITCH_A)])
    assert is_solid(frame_at(frames, 1.5), (200, 0, 0))
    assert is_solid(frame_at(frames, 3), (0, 0, 0))
    assert is_solid(frame_at(frames, 6), (200, 0, 0))
    print("ok  tap Zzz sleeps the display, any button wakes it")


def test_crashing_app_falls_back_to_clock():
    board = make_board(("crashy", "clock"))
    outcome, log, frames, _ = boot(board, 10)
    assert outcome == "running", "a crashing app must not take the board down"
    assert "App 'crashy' crashed - switching to clock" in log, log
    lit = sum(1 for row in frame_at(frames, 9) for px in row if max(px) > 100)
    assert lit > 40, "clock digits should be showing"
    print("ok  a crashing app falls back to the clock; board keeps running")


def test_missing_app_falls_back_to_clock():
    board = make_board(("nosuchapp", "clock"))
    outcome, log, _, _ = boot(board, 3)
    assert outcome == "running" and "switching to clock" in log, log
    print("ok  an app listed in config but missing falls back to the clock")


def test_brightness_saved_until_config_changes():
    board = make_board(("red",))
    _, _, _, b = boot(board, 8, presses=[(2, 1.0, GU.SWITCH_BRIGHTNESS_UP)])
    assert 0.55 < b < 0.65, b                     # 0.3 + 30 frames * 0.01
    _, _, _, b2 = boot(board, 2)
    assert abs(b2 - b) < 0.011, (b, b2)           # remembered after restart
    with open(os.path.join(board, "config.py"), "a") as f:
        f.write("\nBRIGHTNESS = 0.2\n")           # e.g. changed via an update
    _, _, _, b3 = boot(board, 2)
    assert abs(b3 - 0.2) < 1e-6, b3               # new config value wins
    print("ok  button settings persist, but a changed config value wins")


def main():
    cwd = os.getcwd()
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL", t.__name__)
            traceback.print_exc()
        finally:
            os.chdir(cwd)
    print("{} passed, {} failed".format(len(tests) - failed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
