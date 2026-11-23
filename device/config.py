# Galactic Unicorn - settings
#
# This file is delivered by automatic updates from GitHub, so change it in the
# repository rather than on the board. Wi-Fi details live only on the board,
# in secrets.py.
#
# Button changes on the device (theme, brightness, ...) are remembered across
# restarts. If a value here changes, the new value replaces the remembered one
# for that setting.

# ================================================================ system

# Apps, in the order a long press of Zzz cycles through them.
# Each name loads app_<name>.py. The first one runs after a fresh install.
APPS = ("clock",)

# Your STANDARD (winter) offset from UTC, in hours. Half hours are fine (5.5).
#   US Eastern -5 | Central -6 | Mountain -7 | Pacific -8 | Alaska -9 | Hawaii -10
#   UK 0 | Central Europe 1 | Eastern Europe 2 | India 5.5 | Sydney 10
UTC_OFFSET_HOURS = -5

# Daylight saving rule: "US", "EU", "AU", or "NONE"
#   US   - 2nd Sunday in March to 1st Sunday in November (US & Canada)
#   EU   - last Sunday in March to last Sunday in October (UK & Europe)
#   AU   - 1st Sunday in October to 1st Sunday in April (south-east Australia)
#   NONE - no daylight saving (Arizona, Hawaii, India, Japan...)
DST_RULE = "US"

# 0.0 - 1.0. LEDs are very bright on webcams; 0.2 - 0.4 is usually right.
# The LUX +/- buttons adjust this live.
BRIGHTNESS = 0.3

FPS = 30                # animation frame rate (try 20 if animation looks choppy)
WIFI_COUNTRY = "US"     # two-letter country code for Wi-Fi regulations
NTP_HOST = "pool.ntp.org"
RESYNC_HOURS = 6        # how often to re-check the time over the internet

# Automatic updates: the board checks this GitHub repository and installs new
# versions on its own. Set UPDATE_REPO = "" to switch them off.
UPDATE_REPO = "CMYKompany/galactic"
UPDATE_BRANCH = "main"
UPDATE_MINUTES = 10

# Incoming messages: the board listens on this ntfy server for messages sent to
# NTFY_TOPIC (set in secrets.py on the board - the topic works as a password).
NTFY_SERVER = "https://ntfy.sh"

# A one-off message, shown full-screen once after it changes (e.g. when an
# update delivers a new one). Set to "" for none.
ANNOUNCEMENT = "Hello, world"
ANNOUNCEMENT_SECONDS = 5

# ================================================================ clock app

# Starting theme. The A/B/C/D buttons switch between them:
#   A "aurora" - slow drifting northern-lights background, warm white digits
#   B "sky"    - background follows the real sky: dawn, day, dusk, starry night
#   C "amber"  - black background, glowing amber digits (calmest on camera)
#   D "prism"  - black background, slowly drifting rainbow digits
CLOCK_THEME = "aurora"
CLOCK_TWELVE_HOUR = True        # Volume + toggles 12/24 hour
CLOCK_SECONDS = "bar"           # "bar", "digits" or "none" (Volume - cycles)
CLOCK_COLON_PULSE = True        # the colon gently breathes once per second

# Scales background intensity only (digits unaffected). Lower it if the
# background looks washed-out on camera, raise it for more colour.
CLOCK_BACKGROUND_LEVEL = 1.0
