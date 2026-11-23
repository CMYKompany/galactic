# Clock app
#
# Buttons
#   A / B / C / D   theme: aurora / sky / amber / prism
#   Volume +        12 / 24 hour
#   Volume -        seconds style: bar / digits / none

from clockface import ClockFace, THEMES, SECONDS_STYLES, theme_index

THEME_BUTTONS = ("A", "B", "C", "D")


class App:

    def __init__(self, ctx):
        self.ctx = ctx
        c = ctx.cfg
        s = ctx.store
        self.d_theme = c("CLOCK_THEME", "aurora")
        self.d_twelve = bool(c("CLOCK_TWELVE_HOUR", True))
        self.d_seconds = c("CLOCK_SECONDS", "bar")

        self.theme = s.get("clock.theme", self.d_theme)
        self.twelve = bool(s.get("clock.twelve_hour", self.d_twelve))
        self.seconds = s.get("clock.seconds", self.d_seconds)
        if self.seconds not in SECONDS_STYLES:
            self.seconds = "bar"

        self.face = ClockFace(ctx.gfx, level=float(c("CLOCK_BACKGROUND_LEVEL", 1.0)))
        self.colon_pulse = bool(c("CLOCK_COLON_PULSE", True))

    def start(self, now):
        self.face.set_options(self.twelve, self.seconds, self.colon_pulse, now)
        self.face.set_theme(theme_index(self.theme), now)

    def button(self, name, now):
        s = self.ctx.store
        if name in THEME_BUTTONS:
            i = THEME_BUTTONS.index(name)
            self.theme = THEMES[i].name
            self.face.set_theme(i, now)
            s.set("clock.theme", self.theme, self.d_theme, now)
        elif name == "VOL_UP":
            self.twelve = not self.twelve
            self.face.set_options(self.twelve, self.seconds, self.colon_pulse, now)
            s.set("clock.twelve_hour", self.twelve, self.d_twelve, now)
        elif name == "VOL_DOWN":
            i = (SECONDS_STYLES.index(self.seconds) + 1) % len(SECONDS_STYLES)
            self.seconds = SECONDS_STYLES[i]
            self.face.set_options(self.twelve, self.seconds, self.colon_pulse, now)
            s.set("clock.seconds", self.seconds, self.d_seconds, now)

    def quiet(self, now):
        # keep network pauses away from the minute roll-over animation
        lt = self.ctx.local_time(now)
        return lt is None or 5 <= lt[0][5] <= 50

    def frame(self, now, t):
        face = self.face
        lt = self.ctx.local_time(now)
        if lt is not None:
            (_y, _mo, _d, h, mi, s, _wd), frac = lt
            face.set_time(h, mi, s, frac, now)
            tod = h + mi / 60.0 + s / 3600.0
        else:
            face.set_placeholder(now)
            status = self.ctx.net_status()
            face.status = "connecting" if status == "ok" else status
            tod = 21.0  # a pleasant evening sky while waiting
        face.frame(now, t, tod)
