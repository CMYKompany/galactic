# Galactic Unicorn - start-up
#
# CORE FILE: keep this tiny. It runs before anything else so that, whatever
# happens to the apps or launcher, the board can still roll back or fetch a fix.
#
# Start-up order
#   1. ota.boot()   - roll back an update that never started cleanly
#   2. launcher     - runs the apps (also checks GitHub for updates periodically)
#   3. on a crash   - roll back a just-installed update, otherwise wait in
#                     recovery mode for a fixed version to be published

import sys
import ota

try:
    import config
    REPO = getattr(config, "UPDATE_REPO", "")
    BRANCH = getattr(config, "UPDATE_BRANCH", "main")
except Exception:  # noqa: BLE001 - a broken config must not stop recovery
    _st = ota.load_state()
    REPO = _st.get("repo") or ""
    BRANCH = _st.get("branch") or "main"

try:
    from secrets import WIFI_SSID, WIFI_PASSWORD
except ImportError:
    WIFI_SSID = WIFI_PASSWORD = None

updater = ota.Updater(REPO, BRANCH)
updater.boot()

try:
    import launcher
    launcher.run(updater)
except KeyboardInterrupt:
    raise                       # Stop button in Thonny
except Exception as e:  # noqa: BLE001
    sys.print_exception(e)
    if updater.pending():
        print("OTA: new version crashed - rolling back")
        updater.rollback()
        ota._reset()
    ota.recover(updater, WIFI_SSID, WIFI_PASSWORD)
