"""Tests for the over-the-air updater (device/ota.py) and the start-up flow in
device/main.py, run against a fake GitHub and a temporary "board" folder.

    python3 tools/test_ota.py
"""
import datetime as dt
import hashlib
import json
import os
import runpy
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DEVICE = os.path.join(os.path.dirname(HERE), "device")
sys.path.insert(0, os.path.join(HERE, "mock"))

import requests  # noqa: E402  (mock)
from sim import SIM, SimDone, install_time  # noqa: E402

install_time()
sys.print_exception = lambda e: traceback.print_exception(e)

APP_MODULES = ("main", "launcher", "app_clock", "ota", "net", "clockface", "timekeeping",
               "config", "secrets")


# ------------------------------------------------------------------ helpers

def device_files():
    out = {}
    for name in os.listdir(DEVICE):
        if name.endswith(".py") and not name.startswith("secrets"):
            with open(os.path.join(DEVICE, name), "rb") as f:
                out[name] = f.read()
    return out


def release(files):
    """Fake GitHub content for a set of files: manifest + the files."""
    hashes = {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}
    version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
    served = dict(files)
    served["manifest.json"] = json.dumps({"version": version, "files": hashes}).encode()
    return version, served


def make_board(files):
    board = tempfile.mkdtemp(prefix="board-")
    for n, d in files.items():
        with open(os.path.join(board, n), "wb") as f:
            f.write(d)
    with open(os.path.join(board, "secrets.py"), "w") as f:
        f.write('WIFI_SSID = "test"\nWIFI_PASSWORD = "pw"\n')
    return board


def read(board, name):
    try:
        with open(os.path.join(board, name), "rb") as f:
            return f.read()
    except OSError:
        return None


def fresh_ota(board):
    os.chdir(board)
    for m in APP_MODULES:
        sys.modules.pop(m, None)
    sys.path[:] = [p for p in sys.path if not p.startswith(tempfile.gettempdir())]
    sys.path.insert(0, board)
    import ota
    return ota


def run_main(board, seconds, start=dt.datetime(2026, 11, 23, 15, 0, 20)):
    """Boot the board: run main.py until it resets or `seconds` pass."""
    fresh_ota(board)
    SIM.__init__()
    SIM.true_utc0 = start.replace(tzinfo=dt.timezone.utc).timestamp()
    SIM.stop_ms = int(seconds * 1000)
    try:
        runpy.run_path(os.path.join(board, "main.py"), run_name="__main__")
    except SimDone as e:
        return "reset" if "reset" in str(e) else "running"
    return "exited"


def state(board):
    return json.loads(read(board, "ota.json") or b"{}")


# ------------------------------------------------------------------ tests

def test_install_verify_and_confirm():
    v1_files = device_files()
    v1, served1 = release(v1_files)
    board = make_board(v1_files)
    ota = fresh_ota(board)
    requests.serve(served1)
    u = ota.Updater("test/clock")
    assert u.check() == "none" and u.version() == v1  # identical files: just recorded
    u.mark_good()

    v2_files = dict(v1_files, **{"clockface.py": v1_files["clockface.py"] + b"\n# v2\n",
                                 "extra.py": b"X = 1\n"})
    v2, served2 = release(v2_files)
    requests.serve(served2)
    calls_before = len(requests.calls)
    assert u.check() == "installed"
    fetched = [c.split("/")[-1] for c in requests.calls[calls_before:]]
    assert sorted(f for f in fetched if not f.startswith("manifest")) == ["clockface.py", "extra.py"], fetched
    assert read(board, "clockface.py") == v2_files["clockface.py"]
    assert read(board, "clockface.py.bak") == v1_files["clockface.py"]
    assert read(board, "secrets.py") is not None
    assert u.pending() and u.version() == v2
    assert u.check() == "none"
    u.mark_good()
    assert read(board, "clockface.py.bak") is None and not u.pending()
    print("ok  install only changed files, verify, back up, confirm")


def test_bad_fingerprint_changes_nothing():
    files = device_files()
    board = make_board(files)
    ota = fresh_ota(board)
    v2_files = dict(files, **{"launcher.py": files["launcher.py"] + b"\n# v2\n"})
    _, served = release(v2_files)
    served["launcher.py"] = b"tampered"
    requests.serve(served)
    u = ota.Updater("test/clock")
    assert u.check() == "failed"
    assert read(board, "launcher.py") == files["launcher.py"]
    assert not [n for n in os.listdir(board) if n.endswith((".new", ".bak"))]
    print("ok  fingerprint mismatch leaves the board untouched")


def test_unsafe_manifest_rejected():
    files = device_files()
    board = make_board(files)
    ota = fresh_ota(board)
    for bad in ("secrets.py", "../boot.py", "settings.json", ".hidden.py", "lib/x.py"):
        served = {"manifest.json": json.dumps({"version": "x", "files": {bad: "00"}}).encode()}
        requests.serve(served)
        assert ota.Updater("test/clock").check() == "failed", bad
    assert read(board, "secrets.py") == b'WIFI_SSID = "test"\nWIFI_PASSWORD = "pw"\n'
    print("ok  manifest naming secrets/paths/state files is rejected")


def test_no_network_is_harmless():
    files = device_files()
    board = make_board(files)
    ota = fresh_ota(board)
    requests.serve(None)
    assert ota.Updater("test/clock").check() == "failed"
    assert ota.Updater("").check() == "none"
    print("ok  no network / no repo configured")


def test_crashing_update_rolls_back_and_is_skipped():
    v1_files = device_files()
    board = make_board(v1_files)
    v1, served1 = release(v1_files)
    ota = fresh_ota(board)
    requests.serve(served1)
    u = ota.Updater("test/clock")
    u.check()
    u.mark_good()

    broken = dict(v1_files, **{"launcher.py": b"raise RuntimeError('broken release')\n"})
    v2, served2 = release(broken)
    requests.serve(served2)
    assert u.check() == "installed"

    assert run_main(board, 30) == "reset"      # crashes -> rollback -> restart
    assert read(board, "launcher.py") == v1_files["launcher.py"]
    st = state(board)
    assert st["version"] == v1 and v2 in st["bad"] and not st["pending"], st

    ota = fresh_ota(board)
    assert ota.Updater("test/clock").check() == "none"   # never re-installs the bad one
    fixed = dict(v1_files, **{"launcher.py": v1_files["launcher.py"] + b"\n# fixed\n"})
    v3, served3 = release(fixed)
    requests.serve(served3)
    assert ota.Updater("test/clock").check() == "installed"  # but a newer one is fine
    print("ok  crashing update rolls back, is skipped, newer one installs")


def test_repeated_restarts_roll_back():
    v1_files = device_files()
    board = make_board(v1_files)
    v1, served1 = release(v1_files)
    ota = fresh_ota(board)
    requests.serve(served1)
    u = ota.Updater("test/clock")
    u.check()
    u.mark_good()
    v2_files = dict(v1_files, **{"net.py": v1_files["net.py"] + b"\n# v2\n"})
    _, served2 = release(v2_files)
    requests.serve(served2)
    assert u.check() == "installed"
    # simulate power cuts before the update is confirmed
    for _ in range(3):
        ota = fresh_ota(board)
        ota.Updater("test/clock").boot()
    ota = fresh_ota(board)
    try:
        ota.Updater("test/clock").boot()
        raise AssertionError("expected a reset")
    except SimDone:
        pass
    assert read(board, "net.py") == v1_files["net.py"]
    print("ok  update rolled back after 3 unconfirmed restarts")


def test_end_to_end_update_while_running():
    """Clock running v1 finds v2 on 'GitHub', installs it, restarts, then
    confirms it after a clean minute."""
    v1_files = device_files()
    board = make_board(v1_files)
    v1, served1 = release(v1_files)
    ota = fresh_ota(board)
    requests.serve(served1)
    u = ota.Updater("test/clock")
    u.check()
    u.mark_good()

    v2_files = dict(v1_files, **{"clockface.py": v1_files["clockface.py"] + b"\n# v2\n"})
    v2, served2 = release(v2_files)
    requests.serve(served2)
    assert run_main(board, 120) == "reset", "app should install the update and restart"
    assert read(board, "clockface.py") == v2_files["clockface.py"]
    assert state(board)["pending"]

    assert run_main(board, 75) == "running"
    st = state(board)
    assert st["version"] == v2 and not st["pending"], st
    assert read(board, "clockface.py.bak") is None
    print("ok  end to end: running clock updates itself and confirms the update")


def test_broken_clock_recovers_when_fix_published():
    """Not a fresh update, but the clock crashes anyway (e.g. bad config):
    recovery mode keeps checking and installs the fix."""
    files = device_files()
    files["clockface.py"] = b"raise RuntimeError('bug')\n"
    board = make_board(files)
    _, served_same = release(files)
    ota = fresh_ota(board)
    requests.serve(served_same)
    u = ota.Updater("test/clock")
    u.check()
    u.mark_good()
    fixed = device_files()
    _, served_fix = release(fixed)
    requests.serve(served_fix)
    assert run_main(board, 200) == "reset"
    assert read(board, "clockface.py") == fixed["clockface.py"]
    print("ok  crashed clock waits in recovery mode and installs a fix")


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
