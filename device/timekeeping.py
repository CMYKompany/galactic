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

def sync_ntp(host="pool.ntp.org", attempts=3):
    """Set the RTC to UTC from an NTP server. Needs Wi-Fi. Blocks < 1 s per try."""
    import ntptime
    ntptime.host = host
    for _ in range(attempts):
        try:
            ntptime.settime()
            print("Time synced from", host)
            return True
        except Exception as e:  # noqa: BLE001 - OSError / timeout
            print("NTP failed:", e)
    return False
