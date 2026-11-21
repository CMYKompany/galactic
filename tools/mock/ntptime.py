from sim import SIM

host = "pool.ntp.org"


def settime():
    SIM.rtc_epoch = int(SIM.utc_now())
    SIM.rtc_set_ms = SIM.ms - int((SIM.utc_now() % 1) * 1000)
