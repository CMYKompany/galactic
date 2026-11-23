# Galactic Unicorn Clock - settings
#
# Edit the values below, then copy this file to the Unicorn.
# Wi-Fi details live in secrets.py (kept separate so they never end up on GitHub).
#
# Button presses on the device (theme, 12/24h, brightness...) are remembered
# across restarts. If you change a value here, the board picks up your new
# value on the next restart and forgets the button-press overrides.

# ---------------------------------------------------------------- Time zone
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

# ---------------------------------------------------------------- Look
# Starting theme. The A/B/C/D buttons switch between them:
#   A "aurora" - slow drifting northern-lights background, warm white digits
#   B "sky"    - background follows the real sky: dawn, day, dusk, starry night
#   C "amber"  - black background, glowing amber digits (calmest on camera)
#   D "prism"  - black background, slowly drifting rainbow digits
THEME = "aurora"

TWELVE_HOUR = True      # Volume + button toggles 12/24 hour
SECONDS = "bar"         # "bar", "digits" or "none" (Volume - button cycles)
COLON_PULSE = True      # the colon gently breathes once per second

# 0.0 - 1.0. LEDs are very bright on webcams; 0.2 - 0.4 is usually right.
# The LUX +/- buttons adjust this live.
BRIGHTNESS = 0.3

# Scales background intensity only (digits unaffected). Lower it if the
# background looks washed-out on camera, raise it for more colour.
BACKGROUND_LEVEL = 1.0

# ---------------------------------------------------------------- Advanced
WIFI_COUNTRY = "US"     # two-letter country code for Wi-Fi regulations
NTP_HOST = "pool.ntp.org"
RESYNC_HOURS = 6        # how often to re-check the time over the internet
FPS = 30                # animation frame rate

# ---------------------------------------------------------------- Updates
# The board checks this GitHub repository for new versions and installs them
# on its own. Leave UPDATE_REPO empty to switch automatic updates off.
UPDATE_REPO = ""        # "owner/repository"
UPDATE_BRANCH = "main"
UPDATE_MINUTES = 10     # how often to check
