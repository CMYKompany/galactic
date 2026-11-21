from sim import SIM, SimDone


def freq(hz=None):
    return 200_000_000


def reset():
    raise SimDone("machine.reset() called")


class RTC:
    def datetime(self, value=None):
        if value is None:
            return SIM.rtc_fields()
        raise NotImplementedError
