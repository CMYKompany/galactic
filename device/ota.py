# Galactic Unicorn - over-the-air updates from GitHub
#
# CORE FILE: main.py and this file are what make remote updates possible.
# Keep them small, self-contained (no imports from the launcher or apps) and change
# them with extra care.
#
# How it works
#   1. Download device/manifest.json from the GitHub repo: a version id plus
#      a SHA-256 fingerprint for every file that belongs on the board.
#   2. Download each file whose fingerprint differs from the copy on the board
#      to "<name>.new" and verify its fingerprint. Any mismatch aborts the
#      update; nothing on the board changes.
#   3. Swap the files in (old copies kept as "<name>.bak"), mark the update
#      "pending" and restart.
#   4. The clock marks the update good after running cleanly for a minute.
#      If the new version crashes first, or the board restarts 3 times without
#      getting that far, the old files are restored and that version is never
#      installed again (a newer version will be).
#
# Files that belong only to this board are never touched: secrets.py, saved
# settings and this updater's own state.

import gc
import json
import os
import time

STATE_FILE = "ota.json"
PROTECTED = ("secrets.py", "settings.json", STATE_FILE)
# file types an update may deliver (code, data, images, fonts...)
EXTENSIONS = (".py", ".json", ".txt", ".bin", ".jpg", ".png")
MAX_PENDING_BOOTS = 3
USER_AGENT = "galactic-unicorn-clock"


# ================================================================== helpers

def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _hex(digest):
    import binascii
    return binascii.hexlify(digest).decode()


def file_hash(path):
    """SHA-256 of a file as hex, or None if it doesn't exist."""
    import hashlib
    h = hashlib.sha256()
    buf = bytearray(512)
    try:
        with open(path, "rb") as f:
            while True:
                n = f.readinto(buf)
                if not n:
                    break
                h.update(buf[:n] if n < 512 else buf)
    except OSError:
        return None
    return _hex(h.digest())


def _safe_name(name):
    # flat files only, no paths, nothing board-specific
    return (isinstance(name, str) and 0 < len(name) <= 40 and "/" not in name
            and "\\" not in name and not name.startswith(".") and name not in PROTECTED
            and any(name.endswith(e) for e in EXTENSIONS))


def load_state():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
        if isinstance(st, dict):
            return st
    except (OSError, ValueError):
        pass
    return {}


def save_state(st):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f)
    os.rename(tmp, STATE_FILE)   # replace in one step so it's never half-written


def _get(url, timeout=15):
    import requests
    gc.collect()
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except TypeError:   # older requests without timeout support
        r = requests.get(url, headers=headers)
    if r.status_code != 200:
        r.close()
        raise OSError("HTTP {} for {}".format(r.status_code, url))
    return r


# ================================================================== updater

class Updater:

    def __init__(self, repo, branch="main", folder="device"):
        self.enabled = bool(repo) and "/" in repo
        self.base = "https://raw.githubusercontent.com/{}/{}/{}/".format(repo, branch, folder)
        self.state = load_state()
        # remembered so recovery still works if config.py itself is broken
        if self.enabled and (self.state.get("repo") != repo or self.state.get("branch") != branch):
            self.state["repo"] = repo
            self.state["branch"] = branch
            save_state(self.state)

    # ------------------------------------------------------------ status

    def version(self):
        return self.state.get("version", "unknown")

    def pending(self):
        return bool(self.state.get("pending"))

    # ------------------------------------------------------------ boot / health

    def boot(self):
        """Call once at power-on, before loading the clock."""
        if not self.pending():
            return
        boots = self.state.get("boots", 0) + 1
        self.state["boots"] = boots
        save_state(self.state)
        if boots > MAX_PENDING_BOOTS:
            print("OTA: new version never started cleanly - rolling back")
            self.rollback()
            _reset()

    def mark_good(self):
        """The new version ran cleanly: make it permanent and delete backups."""
        if not self.pending():
            return
        for name in self.state.get("backups", []):
            _remove(name + ".bak")
        st = self.state
        st["pending"] = False
        st["boots"] = 0
        st["backups"] = []
        st["added"] = []
        st.pop("prev", None)
        save_state(st)
        print("OTA: version", self.version(), "confirmed")

    def rollback(self):
        st = self.state
        for name in st.get("added", []):
            _remove(name)
        for name in st.get("backups", []):
            if _exists(name + ".bak"):
                _remove(name)
                os.rename(name + ".bak", name)
        bad = st.get("bad", [])
        if st.get("version") and st["version"] not in bad:
            bad.append(st["version"])
        prev = st.get("prev") or {}
        self.state = {"version": prev.get("version"), "files": prev.get("files", {}),
                      "bad": bad[-10:], "pending": False,
                      "repo": st.get("repo"), "branch": st.get("branch")}
        save_state(self.state)
        print("OTA: restored version", self.version())

    # ------------------------------------------------------------ check

    def check(self):
        """Returns "none", "installed" or "failed". Needs Wi-Fi. Blocks for a
        second or two (longer while downloading an update)."""
        if not self.enabled:
            return "none"
        try:
            r = _get(self.base + "manifest.json?t={}".format(time.ticks_ms()))
            try:
                manifest = r.json()
            finally:
                r.close()
            version = manifest["version"]
            files = manifest["files"]
            if not isinstance(files, dict) or not all(_safe_name(n) for n in files):
                raise ValueError("manifest lists a file the updater won't touch")
        except Exception as e:  # noqa: BLE001 - network / JSON / format errors
            print("OTA: check failed:", e)
            return "failed"

        st = self.state
        if version == st.get("version") or version in st.get("bad", []):
            return "none"
        if self.pending():
            return "none"   # let the current update prove itself first

        changed = [n for n in files if file_hash(n) != files[n]]
        removed = [n for n in st.get("files", {}) if n not in files and _safe_name(n)]
        if not changed and not removed:
            # already has these exact files (e.g. copied over by hand): just record it
            st["version"] = version
            st["files"] = files
            save_state(st)
            return "none"
        print("OTA: version {} -> {}: {} changed, {} removed".format(
            st.get("version"), version, len(changed), len(removed)))

        # 1. download + verify everything before touching any live file
        try:
            for name in changed:
                self._download(name, files[name])
        except Exception as e:  # noqa: BLE001
            print("OTA: download failed:", e)
            for name in changed:
                _remove(name + ".new")
            return "failed"

        # 2. record the plan, then swap files in
        backups = [n for n in changed + removed if _exists(n)]
        added = [n for n in changed if not _exists(n)]
        self.state = {"version": version, "files": files, "pending": True, "boots": 0,
                      "backups": backups, "added": added, "bad": st.get("bad", []),
                      "repo": st.get("repo"), "branch": st.get("branch"),
                      "prev": {"version": st.get("version"), "files": st.get("files", {})}}
        save_state(self.state)
        for name in backups:
            _remove(name + ".bak")
            os.rename(name, name + ".bak")
        for name in changed:
            os.rename(name + ".new", name)
        print("OTA: installed version", version)
        return "installed"

    def _download(self, name, expected):
        import hashlib
        r = _get(self.base + name)
        h = hashlib.sha256()
        try:
            with open(name + ".new", "wb") as f:
                while True:
                    chunk = r.raw.read(512)
                    if not chunk:
                        break
                    h.update(chunk)
                    f.write(chunk)
        finally:
            r.close()
        if _hex(h.digest()) != expected:
            raise ValueError("fingerprint mismatch for " + name)


# ================================================================== recovery

def _reset():
    import machine
    time.sleep(1)
    machine.reset()


def _show_error(level):
    """Dim red bar along the bottom edge: 'the launcher or an app has crashed'."""
    try:
        from galactic import GalacticUnicorn
        from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN
        gu = GalacticUnicorn()
        gfx = PicoGraphics(DISPLAY_GALACTIC_UNICORN)
        gfx.set_pen(gfx.create_pen(0, 0, 0))
        gfx.clear()
        gfx.set_pen(gfx.create_pen(level, 0, 0))
        for x in range(20, 33):
            gfx.pixel(x, 10)
        gu.set_brightness(0.3)
        gu.update(gfx)
    except Exception:  # noqa: BLE001 - never let the error display hide the error
        pass


def recover(updater, ssid, password):
    """The launcher or clock crashed and there's no update to roll back. Keep Wi-Fi
    up and check for a fix every minute; restart once one is installed.
    Restarts anyway after 30 minutes in case the fault was temporary."""
    print("OTA: recovery mode - waiting for a fixed version")
    wlan = None
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < 30 * 60 * 1000:
        for level in (60, 25):
            _show_error(level)
            time.sleep(0.5)
        try:
            if ssid and (wlan is None or not wlan.isconnected()):
                import network
                wlan = network.WLAN(network.STA_IF)
                wlan.active(True)
                wlan.connect(ssid, password)
                for _ in range(40):
                    if wlan.isconnected():
                        break
                    time.sleep(0.5)
            if wlan is not None and wlan.isconnected() and updater.check() == "installed":
                _reset()
        except Exception as e:  # noqa: BLE001
            print("OTA: recovery error:", e)
        time.sleep(59)
    _reset()
