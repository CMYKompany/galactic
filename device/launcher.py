# Galactic Unicorn - app launcher and shared services
#
# Started by main.py. Runs one app at a time and provides what every app needs:
# Wi-Fi, the correct local time, automatic updates, brightness, sleep,
# saved settings, and crash isolation.
#
# System buttons (the same in every app)
#   LUX + / LUX -   brightness (hold)
#   Zzz  tap        display off / on (any button also wakes it)
#   Zzz  hold       next app (when config.APPS lists more than one)
# A, B, C, D, Volume + and Volume - belong to the current app.
#
# Writing an app: create app_<name>.py containing
#
#   class App:
#       def __init__(self, ctx): ...          # ctx: Context, below
#       def frame(self, now, t): ...          # draw a full frame into ctx.gfx
#       # optional:
#       def start(self, now): ...             # app became visible
#       def button(self, name, now): ...      # "A" "B" "C" "D" "VOL_UP" "VOL_DOWN"
#       def quiet(self, now): return True     # False = not a good moment for a
#                                             #   brief network pause (animation)
#
# Messages: ctx.notify("text", seconds=5, color=(r, g, b), urgent=False) shows
# a message full-screen over the current app (queued if one is already
# showing; urgent ones go first; long text scrolls), then returns to the app,
# calling its start() again.
#
# then add its name to APPS in config.py. `now` is time.ticks_ms(); `t` is
# seconds since start-up as a float, for animation. The launcher calls
# gu.update() and paces frames; apps just draw.

import json
import sys
import time

import machine
from galactic import GalacticUnicorn
from picographics import PicoGraphics, DISPLAY_GALACTIC_UNICORN as DISPLAY

import config
import text
from inbox import Inbox
from net import WiFi
from timekeeping import TimeKeeper, sync_ntp

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:
    WIFI_SSID = None
    WIFI_PASSWORD = None
try:
    from secrets import NTFY_TOPIC      # incoming messages; the topic is the password
except ImportError:
    NTFY_TOPIC = ""

W = 53
H = 11
FALLBACK_APP = "clock"
BRIGHTNESS_MIN = 0.02
BRIGHTNESS_STEP = 0.01      # per frame while LUX is held
HOLD_MS = 700               # Zzz held this long = next app
HEALTHY_AFTER_MS = 60000    # an update counts as good after running this long


def cfg(name, default=None):
    return getattr(config, name, default)


# =================================================================== settings

class Store:
    """Settings changed with the buttons, saved to flash a few seconds after
    the last change. Each value remembers the config.py value it overrode; if
    config.py has since changed that setting (e.g. via an update), the new
    config.py value wins."""

    FILE = "settings.json"

    def __init__(self):
        self._d = {}
        self._dirty_at = None
        try:
            with open(self.FILE) as f:
                d = json.load(f)
            if isinstance(d, dict):
                self._d = d
        except (OSError, ValueError):
            pass

    def get(self, key, default):
        e = self._d.get(key)
        if isinstance(e, list) and len(e) == 2 and e[1] == str(default):
            return e[0]
        return default

    def set(self, key, value, default, now):
        self._d[key] = [value, str(default)]
        self._dirty_at = now

    def maybe_save(self, now):
        if self._dirty_at is None or time.ticks_diff(now, self._dirty_at) < 3000:
            return
        self._dirty_at = None
        try:
            with open(self.FILE, "w") as f:
                json.dump(self._d, f)
        except OSError as e:
            print("Could not save settings:", e)


# =================================================================== context

class Context:
    """What the launcher shares with apps."""

    def __init__(self, gu, gfx, store, clock, net, notify):
        self.gu = gu
        self.notify = notify
        self.gfx = gfx
        self.width = W
        self.height = H
        self.store = store
        self.clock = clock
        self.net = net

    @staticmethod
    def cfg(name, default=None):
        return cfg(name, default)

    def local_time(self, now):
        """((y, mo, d, h, mi, s, weekday 0=Mon), fraction_of_second), or None
        until the time has been fetched from the internet."""
        if not self.clock.valid():
            return None
        return self.clock.read(now)

    def net_status(self):
        """"ok", "connecting", "error" or "nowifi"."""
        n = self.net
        if not n.enabled:
            return "nowifi"
        if n.connected():
            return "ok"
        if n.connecting() or n.failures == 0:
            return "connecting"
        return "error"


# =================================================================== buttons

GU = GalacticUnicorn
APP_BUTTONS = ((GU.SWITCH_A, "A"), (GU.SWITCH_B, "B"), (GU.SWITCH_C, "C"),
               (GU.SWITCH_D, "D"), (GU.SWITCH_VOLUME_UP, "VOL_UP"),
               (GU.SWITCH_VOLUME_DOWN, "VOL_DOWN"))


class Buttons:
    def __init__(self, gu):
        self.gu = gu
        self.prev = {}

    def tapped(self, switch):
        down = self.gu.is_pressed(switch)
        was = self.prev.get(switch, False)
        self.prev[switch] = down
        return down and not was

    def held(self, switch):
        return self.gu.is_pressed(switch)


# =================================================================== overlay

class Overlay:
    """System indicators drawn on the bottom row, over whatever the app drew."""

    SPAN = 34

    def __init__(self, gfx):
        self.gfx = gfx
        self.kind = None
        self.t0 = 0
        self.value = 0.0
        self.count = 1

    def show(self, kind, now, value=0.0, count=1):
        self.kind = kind
        self.t0 = now
        self.value = value
        self.count = count

    def _px(self, x, r, g, b):
        if 0 <= x < W:
            self.gfx.set_pen(self.gfx.create_pen(int(r), int(g), int(b)))
            self.gfx.pixel(x, H - 1)

    def draw(self, now):
        if self.kind is None:
            return
        age = time.ticks_diff(now, self.t0)
        x0 = (W - self.SPAN) // 2
        if self.kind == "level" and age < 1400:
            # brightness: a level bar, fading out over the last 0.4 s
            fade = 1.0 if age < 1000 else 1.0 - (age - 1000) / 400.0
            n = self.value * self.SPAN
            for k in range(self.SPAN):
                a = 170.0 if k < int(n) else (22.0 + 148.0 * (n - k) if k == int(n) else 22.0)
                a *= fade
                self._px(x0 + k, a, a, a)
        elif self.kind == "update" and age < 2400:
            # update installed: a soft green comet sweeps across, twice
            pos = (age % 1200) / 1200.0 * (W + 8) - 4
            for x in range(W):
                d = pos - x
                if 0.0 <= d < 6.0:
                    f = 1.0 - d / 6.0
                    self._px(x, 90 * f, 255 * f, 140 * f)
        elif self.kind == "apps" and age < 1200:
            # switched app: one dot per app, the current one bright
            fade = 1.0 if age < 900 else 1.0 - (age - 900) / 300.0
            n = self.count
            start = (W - (n * 3 - 2)) // 2
            for i in range(n):
                v = (230.0 if i == int(self.value) else 45.0) * fade
                self._px(start + i * 3, v, v, v)
                self._px(start + i * 3 + 1, v, v, v)
        else:
            self.kind = None


# =================================================================== messages

def _ease(p):
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return 1.0 - (1.0 - p) * (1.0 - p) * (1.0 - p)   # ease-out cubic


class Messages:
    """Full-screen messages over the current app, one at a time."""

    IN_MS = 380
    OUT_MS = 320
    SCROLL_PX_PER_S = 20
    COLOR = (255, 236, 214)
    DESCENDERS = "gjpqy,;"

    def __init__(self, gfx):
        self.gfx = gfx
        self.queue = []
        self.cur = None

    def add(self, msg, seconds=5, color=None, not_before=None, urgent=False):
        """Queue a message. Urgent ones jump the queue and cut short whatever
        message is showing."""
        msg = str(msg).replace("\n", " ")
        if not msg:
            return
        item = (msg, max(1.0, float(seconds)), color or self.COLOR, not_before)
        if urgent:
            self.queue.insert(0, item)
            if self.cur is not None:          # show the interrupted one again after
                c = self.cur
                self.queue.insert(1, (c["msg"], c["seconds"], c["color"], None))
                self.cur = None
        else:
            self.queue.append(item)

    def busy(self):
        return self.cur is not None or bool(self.queue)

    def active(self, now):
        """True while a message owns the display. Starts queued ones."""
        if self.cur is None and self.queue:
            nb = self.queue[0][3]
            if nb is None or time.ticks_diff(now, nb) >= 0:
                msg, seconds, color, _ = self.queue.pop(0)
                width = text.measure(msg)
                scroll = width > W - 2
                if scroll:
                    one_pass = (W + width) * 1000 // self.SCROLL_PX_PER_S
                    passes = max(1, int(seconds * 1000 + one_pass - 1) // one_pass)
                    hold = one_pass * passes
                else:
                    hold = int(seconds * 1000)
                has_desc = False
                for ch in msg:
                    if ch in self.DESCENDERS:
                        has_desc = True
                        break
                self.cur = {"msg": msg, "seconds": seconds, "color": color,
                            "w": width, "scroll": scroll,
                            "t0": now, "hold": hold, "y": 1 if has_desc else 2,
                            "pass_ms": one_pass if scroll else 0}
                print("Message:", msg)
        return self.cur is not None

    def draw(self, now):
        """Draw the current message. Returns False when it has finished."""
        m = self.cur
        gfx = self.gfx
        age = time.ticks_diff(now, m["t0"])
        total = self.IN_MS + m["hold"] + self.OUT_MS
        if age >= total:
            self.cur = None
            return False

        # backdrop: deep blue-black, fading in and out with the message
        if age < self.IN_MS:
            k = _ease(age / self.IN_MS)
        elif age > self.IN_MS + m["hold"]:
            k = 1.0 - _ease((age - self.IN_MS - m["hold"]) / self.OUT_MS)
        else:
            k = 1.0
        gfx.set_pen(gfx.create_pen(int(2 * k), int(3 * k), int(12 * k)))
        gfx.clear()

        c = m["color"]
        y = m["y"]
        if m["scroll"]:
            # enters from the right, leaves on the left, repeating as needed
            t_in = age - self.IN_MS
            if t_in < 0:
                return True
            if t_in >= m["hold"]:
                return True
            x = W - (t_in % m["pass_ms"]) * self.SCROLL_PX_PER_S // 1000
            text.draw(gfx, m["msg"], x, y, c)
        else:
            # rises into place, holds, then rises out of view
            if age < self.IN_MS:
                dy = int((1.0 - _ease(age / self.IN_MS)) * 10 + 0.5)
                fade = _ease(age / self.IN_MS)
            elif age > self.IN_MS + m["hold"]:
                p = (age - self.IN_MS - m["hold"]) / self.OUT_MS
                dy = -int(_ease(p) * 10 + 0.5)
                fade = 1.0 - p
            else:
                dy = 0
                fade = 1.0
            col = (int(c[0] * fade), int(c[1] * fade), int(c[2] * fade))
            text.draw(gfx, m["msg"], (W - m["w"]) // 2, y + dy, col,
                      clip_top=0, clip_bottom=H - 1)

            # countdown: a faint line along the bottom that shrinks to nothing
            if self.IN_MS <= age <= self.IN_MS + m["hold"]:
                left = 1.0 - (age - self.IN_MS) / m["hold"]
                n = int(left * 34 + 0.5)
                x0 = (W - 34) // 2
                gfx.set_pen(gfx.create_pen(c[0] // 5, c[1] // 5, c[2] // 5))
                for i in range(n):
                    gfx.pixel(x0 + i, H - 1)
        return True


# =================================================================== launcher

class Launcher:

    def __init__(self, updater=None):
        try:
            machine.freq(200_000_000)   # same overclock Pimoroni's demos use
        except (ValueError, OSError):
            pass
        self.updater = updater
        self.gu = GalacticUnicorn()
        self.gfx = PicoGraphics(DISPLAY)
        self.store = Store()
        self.brightness = float(self.store.get("system.brightness", cfg("BRIGHTNESS", 0.3)))
        self.gu.set_brightness(min(1.0, max(BRIGHTNESS_MIN, self.brightness)))

        clock = TimeKeeper(cfg("UTC_OFFSET_HOURS", 0), cfg("DST_RULE", "NONE"))
        net = WiFi(WIFI_SSID, WIFI_PASSWORD, country=cfg("WIFI_COUNTRY", ""))
        if not net.enabled:
            print("No Wi-Fi details: copy secrets.example.py to secrets.py and fill it in.")
        self.messages = Messages(self.gfx)
        self.ctx = Context(self.gu, self.gfx, self.store, clock, net, self.messages.add)
        self.buttons = Buttons(self.gu)
        self.overlay = Overlay(self.gfx)
        self.inbox = Inbox(cfg("NTFY_SERVER", "https://ntfy.sh"), NTFY_TOPIC,
                           self._incoming, self.store)
        self._wake = False

        self.apps = [a for a in cfg("APPS", (FALLBACK_APP,))] or [FALLBACK_APP]
        self.app = None
        self.app_name = None

    def _incoming(self, msg, seconds, color, urgent):
        self.messages.add(msg, seconds, color, urgent=urgent)
        if urgent:
            self._wake = True

    # ------------------------------------------------------------ apps

    def open_app(self, name, now):
        self.app = None
        import gc
        gc.collect()
        print("Starting app:", name)
        self.app_name = name          # set first, so a failure is blamed on this app
        mod = __import__("app_" + name)
        self.app = mod.App(self.ctx)
        start = getattr(self.app, "start", None)
        if start:
            start(now)

    def next_app(self, now):
        if len(self.apps) < 2:
            return
        i = (self.apps.index(self.app_name) + 1) % len(self.apps) \
            if self.app_name in self.apps else 0
        self._switch(self.apps[i], now)
        self.store.set("system.app", self.apps[i], self.apps[0], now)
        self.overlay.show("apps", now, value=i, count=len(self.apps))

    def _switch(self, name, now):
        try:
            self.open_app(name, now)
        except Exception as e:  # noqa: BLE001
            self._app_failed(e, now)

    def _app_failed(self, e, now):
        """An app crashed. Fall back to the clock, unless the clock itself or a
        just-installed update is at fault - then let main.py roll back /
        recover."""
        if self.app_name == FALLBACK_APP or (self.updater and self.updater.pending()):
            raise e
        print("App '{}' crashed - switching to {}".format(self.app_name, FALLBACK_APP))
        sys.print_exception(e)
        self.open_app(FALLBACK_APP, now)

    # ------------------------------------------------------------ main loop

    def run(self):
        ctx = self.ctx
        net = ctx.net
        updater = self.updater
        now = time.ticks_ms()

        first = self.store.get("system.app", self.apps[0])
        self._switch(first if first in self.apps else self.apps[0], now)

        ntp_host = cfg("NTP_HOST", "pool.ntp.org")
        ntp_every = int(cfg("RESYNC_HOURS", 6) * 3600000)
        ntp_due = now
        ota_every = int(cfg("UPDATE_MINUTES", 10) * 60000)
        ota_due = time.ticks_add(now, 20000)   # first check shortly after start-up
        started = now

        if updater is not None:
            print("Version", updater.version())
            if updater.pending():
                self.overlay.show("update", now)

        # A one-off announcement from config.py, shown once per new text
        ann = cfg("ANNOUNCEMENT", "")
        if ann and self.store.get("system.announced", "") != ann:
            self.messages.add(ann, cfg("ANNOUNCEMENT_SECONDS", 5),
                              not_before=time.ticks_add(now, 3000))
            self.store.set("system.announced", ann, "", now)
        showing_message = False

        frame_ms = max(10, 1000 // int(cfg("FPS", 30)))
        display_on = True
        zzz_down_at = None
        t = 0.0
        last = now

        while True:
            now = time.ticks_ms()
            t += time.ticks_diff(now, last) / 1000.0
            last = now

            # ------------------------------------------------ network jobs
            # Each blocks the display briefly, so at most one per frame, and
            # only when the app says it's a quiet moment.
            net.poll(now)
            inbox = self.inbox
            if net.connected():
                inbox.poll(now)                   # never blocks
                quiet = getattr(self.app, "quiet", None)
                ok = quiet is None or quiet(now)
                if time.ticks_diff(now, ntp_due) >= 0:
                    ntp_due = time.ticks_add(now, ntp_every if sync_ntp(ntp_host) else 30000)
                elif updater is not None and ok and time.ticks_diff(now, ota_due) >= 0:
                    ota_due = time.ticks_add(now, ota_every)
                    inbox.close()                 # one TLS connection at a time (RAM)
                    if updater.check() == "installed":
                        machine.reset()
                elif ok and inbox.wants_connect(now):
                    inbox.connect(now)
                now = time.ticks_ms()
                last = now
            else:
                inbox.close()

            if self._wake:
                self._wake = False
                if not display_on:
                    display_on = True
                    self._call("start", now)

            if updater is not None and updater.pending() and \
                    time.ticks_diff(now, started) > HEALTHY_AFTER_MS:
                updater.mark_good()

            # ------------------------------------------------ system buttons
            b = self.buttons
            if b.held(GU.SWITCH_SLEEP):
                if zzz_down_at is None:
                    zzz_down_at = now
                elif zzz_down_at != -1 and time.ticks_diff(now, zzz_down_at) >= HOLD_MS:
                    zzz_down_at = -1          # handled: ignore the release
                    display_on = True
                    self.next_app(now)
            elif zzz_down_at is not None:
                if zzz_down_at != -1:         # short tap
                    display_on = not display_on
                    if display_on:
                        self._call("start", now)
                zzz_down_at = None

            if display_on:
                delta = 0.0
                if b.held(GU.SWITCH_BRIGHTNESS_UP):
                    delta += BRIGHTNESS_STEP
                if b.held(GU.SWITCH_BRIGHTNESS_DOWN):
                    delta -= BRIGHTNESS_STEP
                if delta:
                    self.brightness = min(1.0, max(BRIGHTNESS_MIN, self.brightness + delta))
                    self.gu.set_brightness(self.brightness)
                    self.store.set("system.brightness", round(self.brightness, 3),
                                   cfg("BRIGHTNESS", 0.3), now)
                    self.overlay.show("level", now, value=self.brightness)

            # ------------------------------------------------ app buttons
            for switch, name in APP_BUTTONS:
                if b.tapped(switch):
                    if not display_on:
                        display_on = True     # any button wakes the display
                        self._call("start", now)
                    else:
                        self._call("button", name, now)

            self.store.maybe_save(now)

            # ------------------------------------------------ draw
            if display_on:
                if self.messages.active(now) and self.messages.draw(now):
                    showing_message = True
                else:
                    if showing_message:       # a message just ended
                        showing_message = False
                        self._call("start", now)
                    self._call("frame", now, t)
                self.overlay.draw(now)
            else:
                self.gfx.set_pen(self.gfx.create_pen(0, 0, 0))
                self.gfx.clear()
            self.gu.update(self.gfx)

            spent = time.ticks_diff(time.ticks_ms(), now)
            if spent < frame_ms:
                time.sleep_ms(frame_ms - spent)

    def _call(self, method, *args):
        fn = getattr(self.app, method, None)
        if fn is None:
            return
        try:
            fn(*args)
        except Exception as e:  # noqa: BLE001
            self._app_failed(e, time.ticks_ms())


def run(updater=None):
    Launcher(updater).run()
