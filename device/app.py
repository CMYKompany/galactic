# Galactic Unicorn Clock (Pico W or Pico 2 W) - the clock itself
#
# Started by main.py, which also handles updates and crash recovery.
#
# Buttons
#   A / B / C / D   theme: aurora / sky / amber / prism
#   Volume +        12 / 24 hour
#   Volume -        seconds style: bar / digits / none
#   LUX + / LUX -   brightness (hold)
#   Zzz             display off / on
#
# Files on the board: listed in manifest.json, plus secrets.py (Wi-Fi details)

import json
import time

import machine
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN as DISPLAY

import config
from clockface import ClockFace, THEMES, SECONDS_STYLES, theme_index
from net import WiFi
from timekeeping import TimeKeeper, sync_ntp

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:
    WIFI_SSID = None
    WIFI_PASSWORD = None

SETTINGS_FILE = "settings.json"
BRIGHTNESS_MIN = 0.02
BRIGHTNESS_STEP = 0.01      # per frame while LUX is held
HEALTHY_AFTER_MS = 60000    # an update counts as good after running this long


def _cfg(name, default):
    return getattr(config, name, default)


# =================================================================== settings

class Settings:
    """Button-changed preferences, saved to flash a few seconds after the last
    change. Discarded if config.py has been edited since they were saved, so
    edits to config.py always win."""

    def __init__(self):
        self.theme = _cfg("THEME", "aurora")
        self.twelve_hour = bool(_cfg("TWELVE_HOUR", True))
        self.seconds = _cfg("SECONDS", "bar")
        self.brightness = float(_cfg("BRIGHTNESS", 0.3))
        self._dirty_at = None

    @staticmethod
    def _fingerprint():
        return "{}|{}|{}|{}".format(_cfg("THEME", "aurora"), _cfg("TWELVE_HOUR", True),
                                    _cfg("SECONDS", "bar"), _cfg("BRIGHTNESS", 0.3))

    def load(self):
        try:
            with open(SETTINGS_FILE) as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        if d.get("cfg") != self._fingerprint():
            print("config.py changed - using its values")
            return
        if d.get("theme") in [t.name for t in THEMES]:
            self.theme = d["theme"]
        if d.get("seconds") in SECONDS_STYLES:
            self.seconds = d["seconds"]
        if "twelve_hour" in d:
            self.twelve_hour = bool(d["twelve_hour"])
        if "brightness" in d:
            try:
                self.brightness = min(1.0, max(BRIGHTNESS_MIN, float(d["brightness"])))
            except (TypeError, ValueError):
                pass

    def changed(self, now):
        self._dirty_at = now

    def maybe_save(self, now):
        if self._dirty_at is None or time.ticks_diff(now, self._dirty_at) < 3000:
            return
        self._dirty_at = None
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump({"cfg": self._fingerprint(), "theme": self.theme,
                           "twelve_hour": self.twelve_hour, "seconds": self.seconds,
                           "brightness": round(self.brightness, 3)}, f)
        except OSError as e:
            print("Could not save settings:", e)


# =================================================================== buttons

class Buttons:
    """Edge detection for 'tap' buttons; level reading for 'hold' buttons."""

    def __init__(self, gu, taps):
        self.gu = gu
        self.taps = taps
        self.prev = {b: False for b in taps}

    def tapped(self):
        out = []
        for b in self.taps:
            down = self.gu.is_pressed(b)
            if down and not self.prev[b]:
                out.append(b)
            self.prev[b] = down
        return out

    def held(self, b):
        return self.gu.is_pressed(b)


# =================================================================== main

def run(updater=None):
    try:
        machine.freq(200_000_000)   # same overclock Pimoroni's launcher uses
    except (ValueError, OSError):
        pass

    gu = GalacticUnicorn()
    gfx = PicoGraphics(DISPLAY)

    st = Settings()
    st.load()
    gu.set_brightness(st.brightness)

    now = time.ticks_ms()
    face = ClockFace(gfx, level=float(_cfg("BACKGROUND_LEVEL", 1.0)))
    face.set_options(st.twelve_hour, st.seconds, bool(_cfg("COLON_PULSE", True)), now)
    face.set_theme(theme_index(st.theme), now)

    tk = TimeKeeper(_cfg("UTC_OFFSET_HOURS", 0), _cfg("DST_RULE", "NONE"))
    net = WiFi(WIFI_SSID, WIFI_PASSWORD, country=_cfg("WIFI_COUNTRY", ""))
    if not net.enabled:
        print("No Wi-Fi details: copy secrets.example.py to secrets.py and fill it in.")
    ntp_host = _cfg("NTP_HOST", "pool.ntp.org")
    ntp_every = int(_cfg("RESYNC_HOURS", 6) * 3600000)
    ntp_due = now
    ota_every = int(_cfg("UPDATE_MINUTES", 10) * 60000)
    ota_due = time.ticks_add(now, 20000)   # first check shortly after start-up
    started = now

    if updater is not None:
        print("Clock version", updater.version())
        if updater.pending():
            face.celebrate(now)   # a just-installed update: brief sweep along the bottom

    GU = GalacticUnicorn
    theme_buttons = (GU.SWITCH_A, GU.SWITCH_B, GU.SWITCH_C, GU.SWITCH_D)
    buttons = Buttons(gu, theme_buttons + (GU.SWITCH_VOLUME_UP, GU.SWITCH_VOLUME_DOWN,
                                           GU.SWITCH_SLEEP))

    frame_ms = max(10, 1000 // int(_cfg("FPS", 30)))
    display_on = True
    t = 0.0
    last = now

    while True:
        now = time.ticks_ms()
        t += time.ticks_diff(now, last) / 1000.0
        last = now

        net.poll(now)

        # ---------------------------------------------------- network jobs
        # Each blocks briefly, so only one runs per frame, and never while
        # the minute digits are rolling over.
        if net.connected():
            sec = tk.read(now)[0][5] if tk.valid() else 30
            if time.ticks_diff(now, ntp_due) >= 0:
                ntp_due = time.ticks_add(now, ntp_every if sync_ntp(ntp_host) else 30000)
            elif (updater is not None and 5 <= sec <= 50
                    and time.ticks_diff(now, ota_due) >= 0):
                ota_due = time.ticks_add(now, ota_every)
                if updater.check() == "installed":
                    machine.reset()
            now = time.ticks_ms()
            last = now

        if updater is not None and updater.pending() and \
                time.ticks_diff(now, started) > HEALTHY_AFTER_MS:
            updater.mark_good()

        # ---------------------------------------------------- input
        for b in buttons.tapped():
            if b == GU.SWITCH_SLEEP:
                display_on = not display_on
                if display_on:
                    face.reroll(now)
                continue
            if not display_on:
                display_on = True  # any button wakes the display
                face.reroll(now)
                continue
            if b in theme_buttons:
                i = theme_buttons.index(b)
                st.theme = THEMES[i].name
                face.set_theme(i, now)
            elif b == GU.SWITCH_VOLUME_UP:
                st.twelve_hour = not st.twelve_hour
                face.set_options(st.twelve_hour, st.seconds, face.colon_pulse, now)
            elif b == GU.SWITCH_VOLUME_DOWN:
                i = (SECONDS_STYLES.index(st.seconds) + 1) % len(SECONDS_STYLES)
                st.seconds = SECONDS_STYLES[i]
                face.set_options(st.twelve_hour, st.seconds, face.colon_pulse, now)
            st.changed(now)

        if display_on:
            delta = 0.0
            if buttons.held(GU.SWITCH_BRIGHTNESS_UP):
                delta += BRIGHTNESS_STEP
            if buttons.held(GU.SWITCH_BRIGHTNESS_DOWN):
                delta -= BRIGHTNESS_STEP
            if delta:
                st.brightness = min(1.0, max(BRIGHTNESS_MIN, st.brightness + delta))
                gu.set_brightness(st.brightness)
                face.toast(st.brightness, now)
                st.changed(now)

        st.maybe_save(now)

        # ---------------------------------------------------- draw
        if display_on:
            if tk.valid():
                (_y, _mo, _d, h, mi, s, _wd), frac = tk.read(now)
                face.set_time(h, mi, s, frac, now)
                tod = h + mi / 60.0 + s / 3600.0
            else:
                face.set_placeholder(now)
                if not net.enabled:
                    face.status = "nowifi"
                elif net.connecting() or net.failures == 0:
                    face.status = "connecting"
                else:
                    face.status = "error"
                tod = 21.0  # a pleasant evening sky while waiting
            face.frame(now, t, tod)
        else:
            face.blank()
        gu.update(gfx)

        spent = time.ticks_diff(time.ticks_ms(), now)
        if spent < frame_ms:
            time.sleep_ms(frame_ms - spent)
