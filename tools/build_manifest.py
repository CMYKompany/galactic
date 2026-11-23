"""Write device/manifest.json: the list of files the board should have, with a
SHA-256 fingerprint for each, and an overall version id.

    python3 tools/build_manifest.py           # (re)write it
    python3 tools/build_manifest.py --check   # exit 1 if it is out of date

The board's updater (device/ota.py) compares these fingerprints with its own
files and downloads whatever differs.
"""
import hashlib
import json
import os
import sys

DEVICE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "device")
MANIFEST = os.path.join(DEVICE, "manifest.json")
# must match EXTENSIONS in device/ota.py
EXTENSIONS = (".py", ".json", ".txt", ".bin", ".jpg", ".png")
EXCLUDE = {"manifest.json", "secrets.py", "secrets.example.py", "settings.json", "ota.json"}


def build():
    files = {}
    for name in sorted(os.listdir(DEVICE)):
        if name in EXCLUDE or not name.endswith(EXTENSIONS) or name.startswith("."):
            continue
        with open(os.path.join(DEVICE, name), "rb") as f:
            files[name] = hashlib.sha256(f.read()).hexdigest()
    summary = "\n".join("{} {}".format(n, h) for n, h in sorted(files.items()))
    version = hashlib.sha256(summary.encode()).hexdigest()[:12]
    return {"version": version, "files": files}


def main():
    manifest = build()
    text = json.dumps(manifest, indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        try:
            with open(MANIFEST) as f:
                current = f.read()
        except OSError:
            current = ""
        if current != text:
            print("device/manifest.json is out of date - run: python3 tools/build_manifest.py")
            sys.exit(1)
        print("manifest up to date, version", manifest["version"])
        return
    with open(MANIFEST, "w") as f:
        f.write(text)
    print("wrote manifest version", manifest["version"], "with", len(manifest["files"]), "files")


if __name__ == "__main__":
    main()
