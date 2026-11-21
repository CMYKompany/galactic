DISPLAY_GALACTIC_UNICORN = 13


class PicoGraphics:
    def __init__(self, display):
        self.w, self.h = 53, 11
        self.buf = [[(0, 0, 0)] * self.w for _ in range(self.h)]
        self.pen = (0, 0, 0)
        self.calls = 0

    def get_bounds(self):
        return self.w, self.h

    def create_pen(self, r, g, b):
        for v in (r, g, b):
            assert isinstance(v, int) and 0 <= v <= 255, (r, g, b)
        return (r, g, b)

    def set_pen(self, p):
        self.pen = p

    def pixel(self, x, y):
        assert 0 <= x < self.w and 0 <= y < self.h, (x, y)
        self.buf[y][x] = self.pen
        self.calls += 1

    def clear(self):
        self.buf = [[self.pen] * self.w for _ in range(self.h)]

    def set_font(self, name):
        pass
