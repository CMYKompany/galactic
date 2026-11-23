from sim import SIM

STA_IF = 0


def country(c=None):
    return "US"


def hostname(h=None):
    return "galactic-clock"


class WLAN:
    def __init__(self, iface):
        self._active = False
        self._at = None

    def active(self, a=None):
        if a is not None:
            self._active = a
            if not a:
                self._at = None
        return self._active

    def config(self, **kw):
        pass

    def connect(self, ssid, pw):
        assert self._active
        self._at = SIM.ms + SIM.wifi_delay_ms if SIM.wifi_ok else None
        self._fail_at = SIM.ms + 3000

    def isconnected(self):
        return self._at is not None and SIM.ms >= self._at

    def status(self):
        if self.isconnected():
            return 3
        if not SIM.wifi_ok and SIM.ms >= self._fail_at:
            return -1
        return 1

    def ifconfig(self):
        return ("192.168.1.50", "255.255.255.0", "192.168.1.1", "192.168.1.1")

    def disconnect(self):
        self._at = None
