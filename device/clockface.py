# Galactic Unicorn Clock - rendering
#
# Layers, composited per pixel every frame:
#   1. background  - drawn by the active theme (animated)
#   2. halo        - 1px shadow or glow around the digits, for legibility
#   3. digits      - anti-aliased glyphs that roll vertically when they change
#   4. overlay     - colon, seconds bar, status and brightness indicators

import math
import time
import micropython  # noqa: F401  (needed for @micropython.native off-device)

W = 53
H = 11
N = W * H
ZEROS = bytes(N)

ROLL_MS = 420          # digit roll animation length
HALO_NONE = 0
HALO_SHADOW = 1
HALO_GLOW = 2


# =================================================================== helpers

def _ease(p):
    """Ease-in-out cubic, 0..1 -> 0..1."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    if p < 0.5:
        return 4.0 * p * p * p
    q = -2.0 * p + 2.0
    return 1.0 - q * q * q / 2.0


def _smooth(p):
    return p * p * (3.0 - 2.0 * p)


def hsv(h, s, v):
    """h, s in 0..1; v in 0..255. Returns floats."""
    h = h % 1.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i %= 6
    if i == 0:
        return v, t, p
    if i == 1:
        return q, v, p
    if i == 2:
        return p, v, t
    if i == 3:
        return p, q, v
    if i == 4:
        return t, p, v
    return v, p, q


def _lerp3(a, b, p):
    return (a[0] + (b[0] - a[0]) * p,
            a[1] + (b[1] - a[1]) * p,
            a[2] + (b[2] - a[2]) * p)


def _c8(v):
    v = int(v)
    return 0 if v < 0 else (255 if v > 255 else v)


# =================================================================== fonts

class Font:
    """Glyphs drawn as text: '#' = full pixel, '+' = half (anti-aliasing)."""

    def __init__(self, w, h, table):
        self.w = w
        self.h = h
        self.glyphs = {" ": bytearray(w * h)}
        for ch in table:
            rows = table[ch]
            data = bytearray(w * h)
            for y in range(h):
                row = rows[y]
                for x in range(w):
                    c = row[x]
                    data[y * w + x] = 255 if c == "#" else (100 if c == "+" else 0)
            self.glyphs[ch] = data


BIG = Font(6, 9, {
    "0": (".####.", "##..##", "##..##", "##..##", "##..##",
          "##..##", "##..##", "##..##", ".####."),
    "1": ("..##..", ".###..", "####..", "..##..", "..##..",
          "..##..", "..##..", "..##..", ".####."),
    "2": (".####.", "##..##", "....##", "....##", "...##.",
          "..##..", ".##...", "##....", "######"),
    "3": (".####.", "##..##", "....##", "....##", "..###.",
          "....##", "....##", "##..##", ".####."),
    "4": ("##..##", "##..##", "##..##", "##..##", "######",
          "....##", "....##", "....##", "....##"),
    "5": ("######", "##....", "##....", "#####.", "....##",
          "....##", "....##", "##..##", ".####."),
    "6": (".####.", "##..##", "##....", "##....", "#####.",
          "##..##", "##..##", "##..##", ".####."),
    "7": ("######", "....##", "....##", "...##.", "...##.",
          "..##..", "..##..", "..##..", "..##.."),
    "8": (".####.", "##..##", "##..##", "##..##", ".####.",
          "##..##", "##..##", "##..##", ".####."),
    "9": (".####.", "##..##", "##..##", "##..##", ".#####",
          "....##", "....##", "##..##", ".####."),
    "-": ("......", "......", "......", "......", ".####.",
          "......", "......", "......", "......"),
})

SMALL = Font(3, 5, {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
    "-": ("...", "...", "###", "...", "..."),
})


# Layout, relative to the left edge of the digit group:
#   [H][gap][H][gap][:][gap][M][gap][M]  (+ [gap][s][s] in "digits" mode)
BIG_X = (0, 8, 20, 28)
COLON_X = 16
COLON_ROWS = (2, 3, 5, 6)
SMALL_X = (37, 41)
SMALL_DY = 4           # small digits sit on the same baseline as the big ones
GROUP_W_HM = 34
GROUP_W_HMS = 44
LEAD_W = 8             # width of the first hour digit + gap (hidden in 12h mode)


# =================================================================== drawing

@micropython.native
def _blit(cov, g, fw, fh, x0, y0, off, gain):
    """Draw glyph g into coverage map with a fractional vertical offset and
    intensity gain, clipped to the glyph's own box (so rolling digits slide
    out of view)."""
    for ty in range(fh):
        sy = ty - off
        fy = int(math.floor(sy))
        fr = sy - fy
        a0 = fy * fw if 0 <= fy < fh else -1
        a1 = (fy + 1) * fw if 0 <= fy + 1 < fh else -1
        if a0 < 0 and a1 < 0:
            continue
        yy = y0 + ty
        if yy < 0 or yy >= H:
            continue
        row = yy * W
        w0 = 1.0 - fr
        for gx in range(fw):
            xx = x0 + gx
            if xx < 0 or xx >= W:
                continue
            v = 0.0
            if a0 >= 0:
                v += g[a0 + gx] * w0
            if a1 >= 0:
                v += g[a1 + gx] * fr
            iv = int(v * gain)
            if iv > 255:
                iv = 255
            j = row + xx
            if iv > cov[j]:
                cov[j] = iv


@micropython.native
def _halo(cov, halo):
    """1px halo: full strength orthogonally, half strength diagonally."""
    i = 0
    for y in range(H):
        for x in range(W):
            m = 0
            d = 0
            if x > 0:
                v = cov[i - 1]
                if v > m:
                    m = v
                if y > 0:
                    v = cov[i - W - 1]
                    if v > d:
                        d = v
                if y < H - 1:
                    v = cov[i + W - 1]
                    if v > d:
                        d = v
            if x < W - 1:
                v = cov[i + 1]
                if v > m:
                    m = v
                if y > 0:
                    v = cov[i - W + 1]
                    if v > d:
                        d = v
                if y < H - 1:
                    v = cov[i + W + 1]
                    if v > d:
                        d = v
            if y > 0:
                v = cov[i - W]
                if v > m:
                    m = v
            if y < H - 1:
                v = cov[i + W]
                if v > m:
                    m = v
            d >>= 1
            halo[i] = m if m > d else d
            i += 1


class Slot:
    """One character position. Rolls old -> new vertically when it changes."""

    def __init__(self, font):
        self.font = font
        self.cur = " "
        self.prev = " "
        self.t0 = None

    def set(self, ch, now, force=False):
        if ch != self.cur or force:
            self.prev = self.cur
            self.cur = ch
            self.t0 = now
            return True
        return False

    def animating(self, now):
        return self.t0 is not None and time.ticks_diff(now, self.t0) < ROLL_MS

    def draw(self, cov, x, y, now):
        f = self.font
        g = f.glyphs
        if self.t0 is not None:
            p = time.ticks_diff(now, self.t0) / ROLL_MS
            if p < 1.0:
                e = _ease(p)
                d = f.h + 1
                # outgoing digit dims as it leaves, incoming brightens as it lands
                _blit(cov, g.get(self.prev, g[" "]), f.w, f.h, x, y, -e * d, 1.0 - 0.75 * e)
                _blit(cov, g.get(self.cur, g[" "]), f.w, f.h, x, y, (1.0 - e) * d, 0.25 + 0.75 * e)
                return
            self.t0 = None
        _blit(cov, g.get(self.cur, g[" "]), f.w, f.h, x, y, 0.0, 1.0)


# =================================================================== themes

class Theme:
    name = "base"
    halo_mode = HALO_NONE
    halo_k = 0
    accent = (160, 160, 160)

    def background(self, face, t, tod):
        face.bg_r[:] = ZEROS
        face.bg_g[:] = ZEROS
        face.bg_b[:] = ZEROS

    def ink_key(self, t, tod):
        """Return a value that changes when ink() must be re-run, or None
        to re-run it every frame."""
        return 0

    def ink(self, face, t, tod):
        face.fill_ink_rows((255, 255, 255), (255, 255, 255))


class Aurora(Theme):
    name = "aurora"
    halo_mode = HALO_SHADOW
    halo_k = 215
    accent = (110, 230, 200)
    VERT = (1.0, 0.9, 0.8, 0.7, 0.61, 0.53, 0.46, 0.4, 0.35, 0.31, 0.28)

    def background(self, face, t, tod):
        lvl = 80.0 * face.level
        R = face.bg_r
        G = face.bg_g
        B = face.bg_b
        vert = self.VERT
        sin = math.sin
        for x in range(W):
            u = 0.5 * sin(x * 0.11 + t * 0.31) + 0.5 * sin(x * 0.053 - t * 0.17)
            c = 0.5 + 0.5 * sin(x * 0.23 - t * 0.6 + 2.2 * u)
            r, g, b = hsv(0.58 + 0.17 * u, 0.8, lvl * (0.2 + 0.8 * c * c))
            i = x
            for y in range(H):
                k = vert[y]
                R[i] = _c8(r * k)
                G[i] = _c8(g * k)
                B[i] = _c8(b * k)
                i += W

    def ink(self, face, t, tod):
        face.fill_ink_rows((255, 238, 218), (255, 222, 192))


class Sky(Theme):
    """Background follows the time of day. Stars come out at night."""
    name = "sky"
    halo_mode = HALO_SHADOW
    halo_k = 200
    accent = (255, 220, 170)
    #        hour   sky top          horizon          digits
    KEYS = ((0.0,  (2, 3, 16),     (6, 4, 24),      (150, 175, 255)),
            (5.0,  (3, 4, 20),     (26, 10, 34),    (190, 180, 255)),
            (6.5,  (18, 12, 44),   (96, 38, 22),    (255, 214, 170)),
            (8.0,  (14, 38, 74),   (52, 54, 46),    (255, 244, 224)),
            (12.0, (8, 44, 86),    (26, 70, 96),    (255, 250, 236)),
            (16.5, (14, 36, 76),   (60, 52, 44),    (255, 244, 224)),
            (18.5, (36, 14, 54),   (110, 36, 14),   (255, 206, 160)),
            (20.0, (12, 8, 38),    (44, 12, 44),    (214, 190, 255)),
            (22.0, (3, 4, 18),     (10, 6, 28),     (160, 180, 255)),
            (24.0, (2, 3, 16),     (6, 4, 24),      (150, 175, 255)))
    # (x, y, phase) - fixed so the constellation never jumps around
    STARS = ((2, 1, 0.0), (6, 7, 1.7), (11, 3, 4.1), (17, 9, 2.6), (24, 0, 5.3),
             (31, 10, 0.9), (36, 2, 3.4), (41, 8, 5.9), (46, 4, 2.0), (50, 9, 4.6),
             (51, 1, 1.2), (14, 5, 3.0), (27, 6, 0.4), (44, 0, 2.9))

    def _at(self, tod):
        keys = self.KEYS
        for k in range(len(keys) - 1):
            a = keys[k]
            b = keys[k + 1]
            if a[0] <= tod < b[0]:
                p = _smooth((tod - a[0]) / (b[0] - a[0]))
                return _lerp3(a[1], b[1], p), _lerp3(a[2], b[2], p), _lerp3(a[3], b[3], p)
        a = keys[0]
        return a[1], a[2], a[3]

    def background(self, face, t, tod):
        top, bot, _ink = self._at(tod)
        lvl = face.level
        R = face.bg_r
        G = face.bg_g
        B = face.bg_b
        sin = math.sin
        rows = []
        for y in range(H):
            p = y / (H - 1)
            rows.append(_lerp3(top, bot, p * p))
        for x in range(W):
            s = lvl * (1.0 + 0.16 * sin(x * 0.09 + t * 0.15) + 0.06 * sin(x * 0.31 - t * 0.4))
            i = x
            for y in range(H):
                c = rows[y]
                R[i] = _c8(c[0] * s)
                G[i] = _c8(c[1] * s)
                B[i] = _c8(c[2] * s)
                i += W
        # Stars fade in as the sky darkens
        night = 1.0 - (top[0] + top[1] + top[2]) / 60.0
        if night > 0.0:
            for sx, sy, ph in self.STARS:
                tw = 0.55 + 0.45 * sin(t * 1.3 + ph * 2.1)
                a = night * tw * 70.0 * lvl
                i = sy * W + sx
                R[i] = _c8(R[i] + a * 0.85)
                G[i] = _c8(G[i] + a * 0.9)
                B[i] = _c8(B[i] + a)

    def ink_key(self, t, tod):
        return int(tod * 30)  # refresh every 2 minutes

    def ink(self, face, t, tod):
        c = self._at(tod)[2]
        face.fill_ink_rows(c, c)


class Amber(Theme):
    name = "amber"
    halo_mode = HALO_GLOW
    halo_k = 70
    accent = (255, 140, 50)

    def ink(self, face, t, tod):
        face.fill_ink_rows((255, 196, 104), (255, 116, 40))


class Prism(Theme):
    name = "prism"
    halo_mode = HALO_GLOW
    halo_k = 60
    accent = (190, 190, 215)

    def ink_key(self, t, tod):
        return None

    def ink(self, face, t, tod):
        R = face.ink_r
        G = face.ink_g
        B = face.ink_b
        for x in range(W):
            r, g, b = hsv(x * 0.011 + t * 0.045, 0.72, 255.0)
            r = int(r)
            g = int(g)
            b = int(b)
            i = x
            for _ in range(H):
                R[i] = r
                G[i] = g
                B[i] = b
                i += W


THEMES = (Aurora(), Sky(), Amber(), Prism())
SECONDS_STYLES = ("bar", "digits", "none")


def theme_index(name):
    for i in range(len(THEMES)):
        if THEMES[i].name == name:
            return i
    return 0


# =================================================================== face

class ClockFace:

    def __init__(self, gfx, level=1.0):
        self.gfx = gfx
        self.level = level
        self.bg_r = bytearray(N)
        self.bg_g = bytearray(N)
        self.bg_b = bytearray(N)
        self.ink_r = bytearray(N)
        self.ink_g = bytearray(N)
        self.ink_b = bytearray(N)
        self.cov = bytearray(N)
        self.halo = bytearray(N)
        self.ov_a = bytearray(N)
        self.ov_r = bytearray(N)
        self.ov_g = bytearray(N)
        self.ov_b = bytearray(N)
        self._ov_used = []

        self.big = [Slot(BIG) for _ in range(4)]
        self.small = [Slot(SMALL) for _ in range(2)]

        self.theme = THEMES[0]
        self._ink_key = -1
        self.twelve = True
        self.seconds = "bar"
        self.colon_pulse = True

        self._placeholder = True
        self._lead_blank = False
        self._sec = 0
        self._frac = 0.0
        self.status = None          # None | "connecting" | "error" | "nowifi"

        self._layout()
        self._xoff = float(self._x_target)
        self._last_x0 = -999
        self._dirty = True
        self._was_anim = False

    # ------------------------------------------------------------ settings

    def set_theme(self, index, now):
        self.theme = THEMES[index % len(THEMES)]
        self._ink_key = -1
        self.reroll(now)

    def set_options(self, twelve, seconds, colon_pulse, now):
        changed = twelve != self.twelve or seconds != self.seconds
        self.twelve = twelve
        self.seconds = seconds if seconds in SECONDS_STYLES else "bar"
        self.colon_pulse = colon_pulse
        self._layout()
        if changed:
            self.reroll(now)

    def reroll(self, now):
        """Flip every digit in place - visual feedback for a setting change."""
        for s in self.big:
            s.set(s.cur, now, True)
        if self.seconds == "digits":
            for s in self.small:
                s.set(s.cur, now, True)
        self._dirty = True

    # ------------------------------------------------------------ content

    def _layout(self):
        self._group_w = GROUP_W_HMS if self.seconds == "digits" else GROUP_W_HM
        self._y0 = 0 if self.seconds == "bar" else 1
        lead = LEAD_W if self._lead_blank else 0
        self._x_target = (W - (self._group_w - lead)) // 2 - lead
        self._ink_key = -1   # ink gradients depend on the vertical layout
        self._dirty = True

    def set_time(self, h, m, s, frac, now):
        if self.twelve:
            h = h % 12
            if h == 0:
                h = 12
        lead_blank = self.twelve and h < 10
        if lead_blank != self._lead_blank:
            self._lead_blank = lead_blank
            self._layout()
        chars = (" " if lead_blank else str(h // 10), str(h % 10), str(m // 10), str(m % 10))
        for i in range(4):
            if self.big[i].set(chars[i], now):
                self._dirty = True
        if self.seconds == "digits":
            if self.small[0].set(str(s // 10), now) | self.small[1].set(str(s % 10), now):
                self._dirty = True
        self._placeholder = False
        self._sec = s
        self._frac = frac

    def set_placeholder(self, now):
        """Shown until the time is known: dashes, with a status indicator."""
        if self._lead_blank:
            self._lead_blank = False
            self._layout()
        for s in self.big:
            if s.set("-", now):
                self._dirty = True
        for s in self.small:
            if s.set("-", now):
                self._dirty = True
        self._placeholder = True

    # ------------------------------------------------------------ frame

    def frame(self, now, t, tod):
        th = self.theme
        th.background(self, t, tod)
        key = th.ink_key(t, tod)
        if key is None or key != self._ink_key:
            th.ink(self, t, tod)
            self._ink_key = key

        # glide the digit group sideways when the layout width changes
        tx = self._x_target
        self._xoff += (tx - self._xoff) * 0.14
        if abs(tx - self._xoff) < 0.05:
            self._xoff = float(tx)
        x0 = int(self._xoff + 0.5)

        anim = False
        for s in self.big:
            if s.animating(now):
                anim = True
        if self.seconds == "digits":
            for s in self.small:
                if s.animating(now):
                    anim = True
        if anim or self._was_anim or self._dirty or x0 != self._last_x0:
            self._build(now, x0)
            if th.halo_mode != HALO_NONE:
                _halo(self.cov, self.halo)
            self._dirty = False
        self._was_anim = anim
        self._last_x0 = x0

        self._clear_overlay()
        self._draw_colon(x0, t)
        self._draw_bottom(now, x0, t)
        self._push(th.halo_mode, th.halo_k)

    def _build(self, now, x0):
        cov = self.cov
        cov[:] = ZEROS
        y0 = self._y0
        for i in range(4):
            self.big[i].draw(cov, x0 + BIG_X[i], y0, now)
        if self.seconds == "digits":
            for i in range(2):
                self.small[i].draw(cov, x0 + SMALL_X[i], y0 + SMALL_DY, now)

    # ------------------------------------------------------------ overlay

    def _clear_overlay(self):
        oa = self.ov_a
        for i in self._ov_used:
            oa[i] = 0
        self._ov_used = []

    def _ov(self, x, y, c, a):
        if a < 1 or x < 0 or x >= W or y < 0 or y >= H:
            return
        i = y * W + x
        if self.ov_a[i] == 0:
            self._ov_used.append(i)
        self.ov_a[i] = _c8(a)
        self.ov_r[i] = _c8(c[0])
        self.ov_g[i] = _c8(c[1])
        self.ov_b[i] = _c8(c[2])

    def _draw_colon(self, x0, t):
        if self._placeholder:
            a = 70.0 + 50.0 * math.sin(t * 2.4)
        elif self.colon_pulse:
            # brightest on the tick, eases down to 60% mid-second
            a = 255.0 * (0.6 + 0.4 * (0.5 + 0.5 * math.cos(self._frac * 6.2832)))
        else:
            a = 255.0
        y0 = self._y0
        for dy in COLON_ROWS:
            y = y0 + dy
            for dx in (0, 1):
                x = x0 + COLON_X + dx
                i = y * W + x
                self._ov(x, y, (self.ink_r[i], self.ink_g[i], self.ink_b[i]), a)

    def _draw_bottom(self, now, x0, t):
        y = H - 1
        xs = x0 + (LEAD_W if self._lead_blank else 0)
        span = x0 + self._group_w - xs
        acc = self.theme.accent

        # status while the time is unknown
        if self._placeholder:
            if self.status == "connecting":
                # a soft comet sweeping back and forth
                pos = (0.5 + 0.5 * math.sin(t * 2.2)) * (span - 1)
                for k in range(span):
                    d = abs(k - pos)
                    if d < 4.0:
                        self._ov(xs + k, y, acc, 200.0 * (1.0 - d / 4.0))
            elif self.status in ("error", "nowifi"):
                a = 40.0 + 40.0 * math.sin(t * 3.0)
                for k in range(span // 2 - 3, span // 2 + 3):
                    self._ov(xs + k, y, (255, 40, 30), a)
            return

        # seconds bar
        if self.seconds != "bar":
            return
        s = self._sec
        frac = self._frac
        if s == 0 and frac < 0.5:
            # the full bar from the last minute fades away
            fade = 1.0 - frac / 0.5
            for k in range(span):
                self._ov(xs + k, y, acc, 14.0 + 86.0 * fade)
            return
        L = (s + frac) / 60.0 * span
        full = int(L)
        for k in range(span):
            if k < full:
                a = 100.0
            elif k == full:
                a = 14.0 + 86.0 * (L - full)
            else:
                a = 14.0  # faint track
            self._ov(xs + k, y, acc, a)

    # ------------------------------------------------------------ output

    @micropython.native
    def _push(self, mode, k):
        gfx = self.gfx
        pen = gfx.create_pen
        setp = gfx.set_pen
        pix = gfx.pixel
        bgr = self.bg_r
        bgg = self.bg_g
        bgb = self.bg_b
        ir = self.ink_r
        ig = self.ink_g
        ib = self.ink_b
        cov = self.cov
        halo = self.halo
        oa = self.ov_a
        orr = self.ov_r
        og = self.ov_g
        ob = self.ov_b
        i = 0
        for y in range(H):
            for x in range(W):
                r = bgr[i]
                g = bgg[i]
                b = bgb[i]
                h = halo[i]
                if h and mode:
                    if mode == 1:
                        f = 255 - ((h * k) >> 8)
                        r = (r * f) >> 8
                        g = (g * f) >> 8
                        b = (b * f) >> 8
                    else:
                        a = (h * k) >> 8
                        r += (ir[i] * a) >> 8
                        g += (ig[i] * a) >> 8
                        b += (ib[i] * a) >> 8
                        if r > 255:
                            r = 255
                        if g > 255:
                            g = 255
                        if b > 255:
                            b = 255
                a = cov[i]
                if a:
                    na = 255 - a
                    r = (r * na + ir[i] * a) // 255
                    g = (g * na + ig[i] * a) // 255
                    b = (b * na + ib[i] * a) // 255
                a = oa[i]
                if a:
                    na = 255 - a
                    r = (r * na + orr[i] * a) // 255
                    g = (g * na + og[i] * a) // 255
                    b = (b * na + ob[i] * a) // 255
                setp(pen(r, g, b))
                pix(x, y)
                i += 1

    def fill_ink_rows(self, top, bottom):
        """Vertical ink gradient across the digit rows."""
        y0 = self._y0
        for y in range(H):
            p = (y - y0) / 8.0
            if p < 0.0:
                p = 0.0
            elif p > 1.0:
                p = 1.0
            c = _lerp3(top, bottom, p)
            r = _c8(c[0])
            g = _c8(c[1])
            b = _c8(c[2])
            i = y * W
            for _ in range(W):
                self.ink_r[i] = r
                self.ink_g[i] = g
                self.ink_b[i] = b
                i += 1

    def blank(self):
        self.gfx.set_pen(self.gfx.create_pen(0, 0, 0))
        self.gfx.clear()
