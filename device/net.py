# Galactic Unicorn Clock - Wi-Fi connection manager
#
# Keeps the board connected, reconnecting with back-off if the network drops.
# poll() never blocks, so the display keeps animating while connecting.

import time


class WiFi:
    CONNECT_TIMEOUT_MS = 20000

    def __init__(self, ssid, password, country="", hostname="galactic-clock"):
        self.ssid = ssid
        self.password = password
        self.country = country
        self.hostname = hostname
        self.enabled = bool(ssid)
        self.failures = 0
        self._wlan = None
        self._connecting = False
        self._t0 = 0
        self._next = time.ticks_ms()
        self._was_connected = False

    def connected(self):
        return self._wlan is not None and self._wlan.isconnected()

    def connecting(self):
        return self._connecting

    def poll(self, now):
        if not self.enabled:
            return
        if self.connected():
            if not self._was_connected:
                try:
                    ip = self._wlan.ifconfig()[0]
                except Exception:  # noqa: BLE001 - ifconfig() is being phased out
                    ip = ""
                print("Wi-Fi: connected", ip)
                self._was_connected = True
            self._connecting = False
            self.failures = 0
            return
        if self._was_connected:
            print("Wi-Fi: connection lost")
            self._was_connected = False
            self._connecting = False
            self._next = now
        if self._connecting:
            status = self._wlan.status()
            if status < 0:
                print("Wi-Fi: connection failed (status {}). Check secrets.py.".format(status))
                self._fail(now)
            elif time.ticks_diff(now, self._t0) > self.CONNECT_TIMEOUT_MS:
                print("Wi-Fi: timed out connecting to '{}'".format(self.ssid))
                self._fail(now)
        elif time.ticks_diff(now, self._next) >= 0:
            self._begin(now)

    def _begin(self, now):
        try:
            import network
            if self._wlan is None:
                if self.country:
                    try:
                        network.country(self.country)
                    except (AttributeError, ValueError, OSError):
                        pass
                try:
                    network.hostname(self.hostname)
                except (AttributeError, ValueError, OSError):
                    pass
                self._wlan = network.WLAN(network.STA_IF)
            w = self._wlan
            w.active(True)
            try:
                w.config(pm=0xA11140)  # power-saving off: more reliable on some routers
            except (ValueError, OSError):
                pass
            print("Wi-Fi: connecting to '{}'...".format(self.ssid))
            w.connect(self.ssid, self.password)
            self._connecting = True
            self._t0 = now
        except Exception as e:  # noqa: BLE001 - radio errors vary by firmware
            print("Wi-Fi: could not start:", e)
            self._fail(now)

    def _fail(self, now):
        self._connecting = False
        self.failures += 1
        if self._wlan is not None:
            try:
                self._wlan.disconnect()
            except Exception:  # noqa: BLE001
                pass
        # back off: 15 s, 30 s, 45 s ... capped at 5 minutes
        self._next = time.ticks_add(now, min(300000, 15000 * self.failures))
