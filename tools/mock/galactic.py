from sim import SIM, SimDone


class GalacticUnicorn:
    WIDTH = 53
    HEIGHT = 11
    SWITCH_A = 0
    SWITCH_B = 1
    SWITCH_C = 3
    SWITCH_D = 6
    SWITCH_SLEEP = 27
    SWITCH_VOLUME_UP = 7
    SWITCH_VOLUME_DOWN = 8
    SWITCH_BRIGHTNESS_UP = 21
    SWITCH_BRIGHTNESS_DOWN = 26

    def __init__(self):
        self.brightness = 0.5

    def set_brightness(self, b):
        assert 0.0 <= b <= 1.0, b
        self.brightness = b

    def get_brightness(self):
        return self.brightness

    def is_pressed(self, s):
        return SIM.pressed(s)

    def light(self):
        return 120

    def update(self, gfx):
        if SIM.on_frame:
            SIM.on_frame(SIM, gfx.buf, self.brightness)
        if SIM.ms >= SIM.stop_ms:
            raise SimDone()
