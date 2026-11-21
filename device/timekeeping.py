# Galactic Unicorn Clock - time keeping
#
# The board's clock (RTC) is set to UTC over the internet (NTP). Local time,
# including daylight saving, is calculated here from config.py settings, so
# there is nothing to adjust twice a year.
#
# Calendar maths uses its own day-count functions rather than time.mktime so
# results are identical on the board and on a desktop test harness.

import time
import machine


# ------------------------------------------------------------------ calendar

def days_from_civil(y, m, d):
    """Days since 1970-01-01 for a proleptic Gregorian date."""
    if m <= 2:
        y -= 1
    era = y // 400  # Python floor division already rounds toward -inf
    yoe = y - era * 400
    mp = m - 3 if m > 2 else m + 9
    doy = (153 * mp + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    """Inverse of days_from_civil: returns (year, month, day)."""
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = yoe + era * 400
    if m <= 2:
        y += 1
    return y, m, d


def to_epoch(y, mo, d, h=0, mi=0, s=0):
    return days_from_civil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s


def _sunday_index(days):
    """Day of week with 0 = Sunday (1970-01-01 was a Thursday)."""
    return (days + 4) % 7


def nth_sunday(y, m, n):
    first = days_from_civil(y, m, 1)
    return 1 + (7 - _sunday_index(first)) % 7 + 7 * (n - 1)


def last_sunday(y, m):
    nxt = days_from_civil(y + 1, 1, 1) if m == 12 else days_from_civil(y, m + 1, 1)
    month_len = nxt - days_from_civil(y, m, 1)
    return month_len - _sunday_index(nxt - 1)


def dst_active(rule, utc, std):
    """utc: seconds since 1970 (UTC). std: the same instant in local standard time."""
    if rule == "US":
        # 02:00 local standard -> 02:00 local daylight (= 01:00 standard)
        y = civil_from_days(std // 86400)[0]
        start = to_epoch(y, 3, nth_sunday(y, 3, 2), 2)
        end = to_epoch(y, 11, nth_sunday(y, 11, 1), 1)
        return start <= std < end
    if rule == "EU":
        # 01:00 UTC on both changeover days, everywhere in the EU/UK
        y = civil_from_days(utc // 86400)[0]
        start = to_epoch(y, 3, last_sunday(y, 3), 1)
        end = to_epoch(y, 10, last_sunday(y, 10), 1)
        return start <= utc < end
    if rule == "AU":
        # Southern hemisphere: DST spans the new year.
        # Starts 02:00 standard; ends 03:00 daylight (= 02:00 standard).
        y = civil_from_days(std // 86400)[0]
        end = to_epoch(y, 4, nth_sunday(y, 4, 1), 2)
        start = to_epoch(y, 10, nth_sunday(y, 10, 1), 2)
        return std < end or std >= start
    return False


# ------------------------------------------------------------------ clock

class TimeKeeper:
    """Reads the RTC (UTC) and converts it to local wall-clock time."""

    def __init__(self, utc_offset_hours, dst_rule):
        self.rtc = machine.RTC()
        self.offset = int(round(utc_offset_hours * 3600))
        self.rule = (dst_rule or "NONE").upper()
        self._last_s = -1
        self._s_tick = time.ticks_ms()

    def valid(self):
        # An unset RTC starts in 2021 or earlier
        return self.rtc.datetime()[0] >= 2024

    def read(self, now):
        """Returns ((y, mo, d, h, mi, s, weekday 0=Mon), fraction_of_second)."""
        y, mo, d, _wd, h, mi, s, _sub = self.rtc.datetime()

        # The RTC only reports whole seconds; estimate the fraction from ticks
        if s != self._last_s:
            self._last_s = s
            self._s_tick = now
        frac = time.ticks_diff(now, self._s_tick) / 1000
        if frac < 0:
            frac = 0.0
        elif frac > 0.999:
            frac = 0.999

        utc = to_epoch(y, mo, d, h, mi, s)
        std = utc + self.offset
        local = std + (3600 if dst_active(self.rule, utc, std) else 0)
        days, sod = divmod(local, 86400)
        ly, lm, ld = civil_from_days(days)
        return (ly, lm, ld, sod // 3600, (sod // 60) % 60, sod % 60, (days + 3) % 7), frac


# ------------------------------------------------------------------ network

class WiFiSync:
    """Non-blocking Wi-Fi + NTP state machine, polled once per frame.

    Connecting never freezes the display: poll() returns immediately and the
    only blocking step is the NTP request itself (well under a second).
    Wi-Fi is switched off between syncs.
    """

    IDLE = 0
    CONNECTING = 1
    CONNECT_TIMEOUT_MS = 20000

    def __init__(self, ssid, password, country="", host="pool.ntp.org",
                 resync_hours=6, hostname="galactic-clock"):
        self.ssid = ssid
        self.password = password
        self.country = country
        self.host = host
        self.hostname = hostname
        self.resync_ms = int(resync_hours * 3600 * 1000)
        self.enabled = bool(ssid)
        self.state = self.IDLE
        self.synced_once = False
        self.failures = 0
        self._wlan = None
        self._t0 = 0
        self._next = time.ticks_ms()

    def connecting(self):
        return self.state == self.CONNECTING

    def poll(self, now):
        if not self.enabled:
            return
        if self.state == self.IDLE:
            if time.ticks_diff(now, self._next) >= 0:
                self._begin(now)
            return

        w = self._wlan
        if w.isconnected():
            self._finish(self._sync())
        elif w.status() < 0:
            print("Wi-Fi: connection failed (status {}). Check secrets.py.".format(w.status()))
            self._finish(False)
        elif time.ticks_diff(now, self._t0) > self.CONNECT_TIMEOUT_MS:
            print("Wi-Fi: timed out connecting to '{}'".format(self.ssid))
            self._finish(False)

    def _begin(self, now):
        try:
            import network
            if self.country:
                try:
                    network.country(self.country)
                except (AttributeError, ValueError, OSError):
                    pass
            try:
                network.hostname(self.hostname)
            except (AttributeError, ValueError, OSError):
                pass
            w = network.WLAN(network.STA_IF)
            w.active(True)
            try:
                w.config(pm=0xA11140)  # power-saving off: more reliable on some routers
            except (ValueError, OSError):
                pass
            print("Wi-Fi: connecting to '{}'...".format(self.ssid))
            w.connect(self.ssid, self.password)
            self._wlan = w
            self._t0 = now
            self.state = self.CONNECTING
        except Exception as e:  # noqa: BLE001 - radio errors vary by firmware
            print("Wi-Fi: could not start:", e)
            self._wlan = None
            self._finish(False)

    def _sync(self):
        import ntptime
        ntptime.host = self.host
        for _ in range(3):
            try:
                ntptime.settime()
                print("Time synced from", self.host)
                return True
            except Exception as e:  # noqa: BLE001 - OSError / timeout
                print("NTP failed:", e)
        return False

    def _finish(self, ok):
        if self._wlan is not None:
            try:
                self._wlan.disconnect()
                self._wlan.active(False)
            except Exception:  # noqa: BLE001
                pass
        self.state = self.IDLE
        if ok:
            self.synced_once = True
            self.failures = 0
            delay = self.resync_ms
        else:
            self.failures += 1
            # back off: 15 s, 30 s, 45 s ... capped at 5 minutes
            delay = min(300000, 15000 * self.failures)
        self._next = time.ticks_add(time.ticks_ms(), delay)
