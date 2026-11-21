"""Checks the board's local-time maths against Python's time zone database.

    python3 tools/test_timekeeping.py

Walks every 30 minutes across 2025-2035 (plus every minute around each
changeover) for each supported DST rule and compares the result.
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "mock"), os.path.join(os.path.dirname(HERE), "device")]

import timekeeping as tk  # noqa: E402

CASES = [  # (tz name, standard offset, rule)
    ("America/New_York", -5, "US"),
    ("America/Los_Angeles", -8, "US"),
    ("America/Phoenix", -7, "NONE"),
    ("Europe/London", 0, "EU"),
    ("Europe/Berlin", 1, "EU"),
    ("Australia/Sydney", 10, "AU"),
    ("Asia/Kolkata", 5.5, "NONE"),
]


def local_from_board(utc_epoch, offset, rule):
    off = int(round(offset * 3600))
    std = utc_epoch + off
    loc = std + (3600 if tk.dst_active(rule, utc_epoch, std) else 0)
    days, sod = divmod(loc, 86400)
    y, m, d = tk.civil_from_days(days)
    return (y, m, d, sod // 3600, (sod // 60) % 60)


def main():
    # calendar round trip
    for z in range(-800000, 800000, 37):
        assert tk.days_from_civil(*tk.civil_from_days(z)) == z
    assert tk.days_from_civil(1970, 1, 1) == 0

    start = int(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    end = int(dt.datetime(2036, 1, 1, tzinfo=dt.timezone.utc).timestamp())
    failures = 0
    checked = 0
    for name, offset, rule in CASES:
        zone = ZoneInfo(name)
        prev = None
        t = start
        while t < end:
            want_dt = dt.datetime.fromtimestamp(t, zone)
            want = (want_dt.year, want_dt.month, want_dt.day, want_dt.hour, want_dt.minute)
            got = local_from_board(t, offset, rule)
            checked += 1
            if got != want:
                failures += 1
                if failures < 10:
                    print("MISMATCH", name, dt.datetime.fromtimestamp(t, dt.timezone.utc), got, want)
            # around a changeover, check every minute of the surrounding 2 hours
            off_now = want_dt.utcoffset()
            if prev is not None and off_now != prev:
                for u in range(t - 7200, t + 7200, 60):
                    w = dt.datetime.fromtimestamp(u, zone)
                    checked += 1
                    if local_from_board(u, offset, rule) != (w.year, w.month, w.day, w.hour, w.minute):
                        failures += 1
                        print("MISMATCH near changeover", name, u)
            prev = off_now
            t += 1800
    print("checked {} instants, {} mismatches".format(checked, failures))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
