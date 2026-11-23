"""Shared simulation state for the desktop mock of the Galactic Unicorn."""
import datetime as _dt


class SimDone(BaseException):
    """Raised to end a simulation (BaseException so the app can't swallow it)."""


class Sim:
    def __init__(self):
        self.ms = 0
        self.true_utc0 = 0          # real UTC epoch at ms == 0
        self.rtc_epoch = None       # RTC value set at rtc_set_ms (None = unset)
        self.rtc_set_ms = 0
        self.wifi_ok = True
        self.wifi_delay_ms = 1500
        self.presses = []           # (start_ms, end_ms, switch)
        self.stop_ms = 10_000
        self.on_frame = None        # callback(sim, pixels, brightness)

    def utc_now(self):
        return self.true_utc0 + self.ms / 1000

    def rtc_fields(self):
        if self.rtc_epoch is None:
            e = _dt.datetime(2021, 1, 1).replace(tzinfo=_dt.timezone.utc).timestamp() + self.ms / 1000
        else:
            e = self.rtc_epoch + (self.ms - self.rtc_set_ms) / 1000
        d = _dt.datetime.fromtimestamp(int(e), _dt.timezone.utc)
        return (d.year, d.month, d.day, d.weekday(), d.hour, d.minute, d.second, 0)

    def pressed(self, switch):
        return any(a <= self.ms < b and s == switch for a, b, s in self.presses)


SIM = Sim()


def install_time():
    """Replace MicroPython-only time functions with versions driven by SIM.ms."""
    import time
    mask = (1 << 30) - 1

    def ticks_diff(a, b):
        d = (a - b) & mask
        return d - (1 << 30) if d >= (1 << 29) else d

    def sleep_ms(ms):
        SIM.ms += int(ms)

    time.ticks_ms = lambda: SIM.ms & mask
    time.ticks_add = lambda a, b: (a + b) & mask
    time.ticks_diff = ticks_diff
    time.sleep_ms = sleep_ms
    time.sleep = lambda s: sleep_ms(s * 1000)
