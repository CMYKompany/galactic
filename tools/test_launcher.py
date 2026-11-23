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
        self.ctx = ctx
    def button(self, name, now):
        if name == "A":
            self.ctx.notify("First", 2)
            self.ctx.notify("Second", 2, color=(0, 255, 0))
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
           "clockface", "timekeeping", "text", "inbox", "config", "secrets")
MSG = (255, 236, 214)   # default message colour


def make_board(apps, extra_config=""):
    board = tempfile.mkdtemp(prefix="board-")
    for name in os.listdir(DEVICE):
        if name.endswith(".py") and not name.startswith("secrets"):
            with open(os.path.join(DEVICE, name), "rb") as f:
                data = f.read()
            if name == "config.py":
                data += "\nAPPS = {!r}\nUPDATE_REPO = ''\nANNOUNCEMENT = ''\n{}\n".format(
                    apps, extra_config).encode()
            with open(os.path.join(board, name), "wb") as f:
                f.write(data)
    for name, data in (("app_red.py", RED_APP), ("app_crashy.py", CRASHY_APP)):
        with open(os.path.join(board, name), "wb") as f:
            f.write(data)
    with open(os.path.join(board, "secrets.py"), "w") as f:
        f.write('WIFI_SSID = "test"\nWIFI_PASSWORD = "pw"\n')
    return board


def boot(board, seconds, presses=(), before=None):
    """Run main.py; returns (outcome, stdout, frames {ms: buf}, final brightness)."""
    os.chdir(board)
    for m in MODULES:
        sys.modules.pop(m, None)
    sys.path[:] = [p for p in sys.path if not p.startswith(tempfile.gettempdir())]
    sys.path.insert(0, board)
    if before:
        before()
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


def has_color(buf, color):
    return any(px == color for row in buf for px in row)


def test_announcement_shows_once_then_returns_to_app():
    board = make_board(("red",), 'ANNOUNCEMENT = "Hello, world"\nANNOUNCEMENT_SECONDS = 5')
    _, log, frames, _ = boot(board, 12)
    assert "Message: Hello, world" in log, log
    assert is_solid(frame_at(frames, 2), (200, 0, 0))          # app first
    assert has_color(frame_at(frames, 5), MSG)                 # message after ~3 s
    assert not has_color(frame_at(frames, 5), (200, 0, 0))
    assert is_solid(frame_at(frames, 10), (200, 0, 0))         # back to the app
    _, log, frames, _ = boot(board, 8)                         # restart
    assert "Message:" not in log, "announcement must only show once"
    print("ok  announcement shows once, then the app resumes")


def test_apps_can_queue_messages():
    board = make_board(("red",))
    _, log, frames, _ = boot(board, 9, presses=[(1, 0.1, GU.SWITCH_A)])
    assert log.index("Message: First") < log.index("Message: Second"), log
    assert has_color(frame_at(frames, 2.5), MSG)
    assert has_color(frame_at(frames, 5), (0, 255, 0))         # second, in its colour
    assert is_solid(frame_at(frames, 8.5), (200, 0, 0))
    print("ok  apps can queue messages; each shows in turn")


def test_long_message_scrolls():
    board = make_board(("red",), 'ANNOUNCEMENT = "This message is far too long to fit"\n'
                                 'ANNOUNCEMENT_SECONDS = 2')
    _, _, frames, _ = boot(board, 12)

    def columns(buf):
        return [tuple(buf[y][x] == MSG for y in range(10)) for x in range(53)]

    a, b = columns(frame_at(frames, 6)), columns(frame_at(frames, 7))
    # one second later the same columns appear ~20 px further left
    best = max(range(0, 30), key=lambda d: sum(a[x] == b[x - d] for x in range(d, 53)))
    assert 17 <= best <= 23, best
    print("ok  long messages scroll")


class FakeNtfy:
    """Stand-in for the ntfy stream: releases scripted lines at scripted times."""

    def __init__(self, events):
        self.events = list(events)          # [(seconds, dict)]
        self.sent = b""
        self.head = False

    def write(self, b):
        self.sent += b

    def setblocking(self, flag):
        pass

    def read(self, n):
        if not self.head:
            self.head = True
            return b"HTTP/1.0 200 OK\r\n\r\n"
        if self.events and SIM.ms >= self.events[0][0] * 1000:
            ev = self.events.pop(0)[1]
            return (json.dumps(ev) + "\n").encode()
        return None

    def close(self):
        pass


def test_ntfy_message_shows_and_urgent_wakes_display():
    board = make_board(("red",))
    with open(os.path.join(board, "secrets.py"), "a") as f:
        f.write('NTFY_TOPIC = "test-topic"\n')
    stream = FakeNtfy([
        (4, {"id": "m1", "time": 1, "event": "message", "message": "Lunch is here"}),
        (12, {"id": "m2", "time": 2, "event": "message", "message": "Server down",
              "priority": 5}),
    ])

    def patch():
        import inbox
        inbox._open_socket = lambda host, port, tls: stream

    _, log, frames, _ = boot(board, 34, presses=[(9, 0.1, GU.SWITCH_SLEEP)], before=patch)
    assert b"GET /test-topic/json HTTP/1.0" in stream.sent, stream.sent
    assert "Message: Lunch is here" in log, log
    assert has_color(frame_at(frames, 6), MSG)
    assert is_solid(frame_at(frames, 11), (0, 0, 0))              # asleep
    assert has_color(frame_at(frames, 14), (255, 70, 60))         # urgent: woke, red
    assert log.count("Message: Lunch is here") == 2, log           # interrupted one re-shown
    print("ok  ntfy messages show; urgent ones wake a sleeping display")


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
