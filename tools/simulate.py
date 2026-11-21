"""Run the real device code on the desktop against mock hardware and render
an animated preview (MP4) plus still frames.

    python3 tools/simulate.py OUT_DIR

Uses a simulated clock, so a 40-second scenario renders in a few seconds.
"""
import datetime as dt
import os
import runpy
import sys
import tempfile
import time

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(HERE, "mock"), os.path.join(ROOT, "device")]

from sim import SIM, SimDone  # noqa: E402
import galactic  # noqa: E402

GU = galactic.GalacticUnicorn

# ------------------------------------------------------------ simulated time
_MASK = (1 << 30) - 1
time.ticks_ms = lambda: SIM.ms & _MASK
time.ticks_add = lambda a, b: (a + b) & _MASK


def _ticks_diff(a, b):
    d = (a - b) & _MASK
    return d - (1 << 30) if d >= (1 << 29) else d


def _sleep_ms(ms):
    SIM.ms += int(ms)


time.ticks_diff = _ticks_diff
time.sleep_ms = _sleep_ms
time.sleep = lambda s: _sleep_ms(s * 1000)
sys.print_exception = lambda e: __import__("traceback").print_exception(e)

# ------------------------------------------------------------ LED rendering
SCALE = 12


def render(pixels, scale=SCALE):
    w, h = 53, 11
    pad = scale
    img = Image.new("RGB", (w * scale + pad * 2, h * scale + pad * 2), (8, 8, 10))
    d = ImageDraw.Draw(img)
    r = scale * 0.36
    for y in range(h):
        for x in range(w):
            c = pixels[y][x]
            cx = pad + x * scale + scale / 2
            cy = pad + y * scale + scale / 2
            lit = max(c) > 0
            fill = c if lit else (22, 22, 26)
            d.rounded_rectangle((cx - r, cy - r, cx + r, cy + r), radius=r * 0.45, fill=fill)
    # screen-blend a softened copy for a subtle LED bloom
    glow = img.filter(ImageFilter.GaussianBlur(scale * 0.55))
    glow = Image.eval(glow, lambda v: int(v * 0.75))
    return ImageChops.screen(img, glow)


# ------------------------------------------------------------ scenario
def run(start_utc, stop_s, presses=(), wifi_ok=True, capture_every=2, stills=()):
    """presses: (at_seconds, duration_seconds, switch). stills: seconds to snapshot."""
    SIM.__init__()
    SIM.true_utc0 = start_utc.replace(tzinfo=dt.timezone.utc).timestamp()
    SIM.stop_ms = int(stop_s * 1000)
    SIM.wifi_ok = wifi_ok
    SIM.presses = [(int(a * 1000), int((a + d) * 1000), s) for a, d, s in presses]
    frames, snaps = [], {}
    pending = sorted(stills)
    count = [0]

    def on_frame(sim, buf, brightness):
        count[0] += 1
        copy = [row[:] for row in buf]
        if count[0] % capture_every == 0:
            frames.append((sim.ms, copy))
        while pending and sim.ms >= pending[0] * 1000:
            snaps[pending.pop(0)] = copy

    SIM.on_frame = on_frame
    for m in ("main", "clockface", "timekeeping", "config", "secrets"):
        sys.modules.pop(m, None)
    try:
        runpy.run_path(os.path.join(ROOT, "device", "main.py"), run_name="__main__")
    except SimDone:
        pass
    return frames, snaps, count[0]


def save_video(frames, path, fps=15):
    """Encode captured frames to H.264 MP4 with ffmpeg."""
    import subprocess
    first = render(frames[0][1])
    w, h = first.size
    w -= w % 2
    h -= h % 2
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", "{}x{}".format(w, h), "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", path],
        stdin=subprocess.PIPE)
    for _, f in frames:
        proc.stdin.write(render(f).crop((0, 0, w, h)).tobytes())
    proc.stdin.close()
    proc.wait()


def main():
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "preview")
    os.makedirs(out, exist_ok=True)
    work = tempfile.mkdtemp()
    with open(os.path.join(work, "secrets.py"), "w") as f:
        f.write('WIFI_SSID = "test"\nWIFI_PASSWORD = "test"\n')
    sys.path.insert(0, work)
    os.chdir(work)

    # 1. Boot -> Wi-Fi -> 9:59 rolls over to 10:00, then a theme tour
    #    14:59:48 UTC = 9:59:48 EST
    frames, snaps, n = run(
        dt.datetime(2026, 11, 21, 14, 59, 48), 44,
        presses=[(16, 0.1, GU.SWITCH_B), (22, 0.1, GU.SWITCH_C), (28, 0.1, GU.SWITCH_D),
                 (34, 0.1, GU.SWITCH_VOLUME_DOWN), (38, 0.6, GU.SWITCH_BRIGHTNESS_UP),
                 (40.5, 0.1, GU.SWITCH_A)],
        stills=[0.9, 14, 21, 27, 33, 37, 38.4, 43])
    print("tour: frames rendered", n, "captured", len(frames))
    save_video(frames, os.path.join(out, "tour.mp4"))
    for s, f in snaps.items():
        render(f).save(os.path.join(out, "tour_{:05.1f}s.png".format(s)))

    # 2. Sky theme across the day (fresh settings so config defaults apply)
    for name in ("settings.json",):
        if os.path.exists(name):
            os.remove(name)
    for hh in (6, 7, 12, 18, 19, 23):
        utc = dt.datetime(2026, 11, 21, hh, 30) + dt.timedelta(hours=5)
        _, snaps, _ = run(utc, 6.0, presses=[(3, 0.1, GU.SWITCH_B)], stills=[5.5])
        render(snaps[5.5]).save(os.path.join(out, "sky_{:02d}30.png".format(hh)))
        if os.path.exists("settings.json"):
            os.remove("settings.json")

    # 3. No Wi-Fi reachable: dashes with error indicator
    _, snaps, _ = run(dt.datetime(2026, 11, 21, 15, 0), 8, wifi_ok=False, stills=[7])
    render(snaps[7]).save(os.path.join(out, "wifi_error.png"))
    print("wrote", out)


if __name__ == "__main__":
    main()
