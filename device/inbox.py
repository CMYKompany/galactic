# Galactic Unicorn - incoming messages from ntfy (https://ntfy.sh)
#
# Keeps one streaming connection open to <server>/<topic>/json. New messages
# arrive within a second of being sent. The connection is read without
# blocking once per frame, so animation never pauses for it; only opening the
# connection blocks briefly (DNS + TLS handshake, ~1-2 s), which the launcher
# schedules for quiet moments.
#
# Sending a message (anything that can make a web request works):
#   curl -d "Lunch is here" https://ntfy.sh/<topic>
#   curl -H "Title: Build" -H "Priority: high" -d "Deploy finished" https://ntfy.sh/<topic>
# or the ntfy phone app, subscribed to the same topic.
#
# The topic acts as the password: it lives only in secrets.py on the board.
#
# Priority (header "Priority: 1..5" or min/low/default/high/urgent) sets how
# a message looks:
#   1-2  4 s, dimmer            3  6 s (default)
#   4    10 s, amber            5  15 s, red, and wakes a sleeping display
# A tag naming a colour (red, orange, amber, yellow, green, cyan, blue,
# purple, pink, white) overrides the colour.

import json
import time

STALE_MS = 120000           # ntfy sends a keepalive every ~45 s
MAX_TEXT = 240
COLORS = {"red": (255, 70, 60), "orange": (255, 140, 40), "amber": (255, 180, 70),
          "yellow": (255, 230, 90), "green": (110, 255, 140), "cyan": (90, 230, 255),
          "blue": (110, 150, 255), "purple": (190, 120, 255), "pink": (255, 120, 200),
          "white": (255, 255, 255)}
STYLE = {1: (4, (170, 160, 150)), 2: (4, (200, 190, 175)), 3: (6, None),
         4: (10, (255, 180, 70)), 5: (15, (255, 70, 60))}
_ASCII = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
          "—": "-", "…": "...", " ": " ", "•": "*", "°": "o",
          "\n": " ", "\r": " ", "\t": " "}


def to_ascii(s):
    out = []
    for ch in s:
        if " " <= ch <= "~":
            out.append(ch)
        else:
            out.append(_ASCII.get(ch, "?"))
    return "".join(out)


def _open_socket(host, port, use_tls):
    import socket
    ai = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0]
    s = socket.socket(ai[0], socket.SOCK_STREAM, ai[2])
    s.settimeout(10)
    s.connect(ai[-1])
    if use_tls:
        try:
            import tls
            ctx = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
            ctx.verify_mode = tls.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=host)
        except ImportError:
            import ssl
            s = ssl.wrap_socket(s, server_hostname=host)
    return s


class Inbox:

    def __init__(self, server, topic, on_message, store=None, opener=None):
        server = (server or "").rstrip("/")
        self.enabled = bool(server and topic)
        self.use_tls = server.startswith("https://")
        hostport = server.split("://", 1)[-1]
        if ":" in hostport:
            self.host, port = hostport.split(":", 1)
            self.port = int(port)
        else:
            self.host = hostport
            self.port = 443 if self.use_tls else 80
        self.topic = topic
        self.on_message = on_message
        self.store = store
        self._open = opener or _open_socket
        self.sock = None
        self.failures = 0
        self._next_try = time.ticks_ms()
        self._last_rx = 0
        self._raw = b""
        self._buf = b""
        self._state = "headers"     # headers -> body, or headers -> size <-> data
        self._chunked = False
        self._chunk_left = 0
        saved = store.get("inbox.seen", "") if store else ""
        self._seen = saved.split(",") if saved else []
        self._since = store.get("inbox.since", "") if store else ""

    # ------------------------------------------------------------ connection

    def wants_connect(self, now):
        return (self.enabled and self.sock is None
                and time.ticks_diff(now, self._next_try) >= 0)

    def connect(self, now):
        """Open the stream. Blocks for DNS + TLS (~1-2 s). Needs Wi-Fi."""
        path = "/{}/json".format(self.topic)
        if self._since:
            path += "?since=" + self._since
        try:
            import gc
            gc.collect()
            s = self._open(self.host, self.port, self.use_tls)
            s.write("GET {} HTTP/1.0\r\nHost: {}\r\nUser-Agent: galactic-unicorn\r\n"
                    "Accept: application/x-ndjson\r\n\r\n".format(path, self.host).encode())
            s.setblocking(False)
        except Exception as e:  # noqa: BLE001 - DNS / TLS / socket errors
            print("Inbox: connect failed:", e)
            self._fail(now)
            return False
        self.sock = s
        self._raw = b""
        self._buf = b""
        self._state = "headers"
        self._chunked = False
        self._last_rx = now
        print("Inbox: listening on", self.host)
        return True

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:  # noqa: BLE001
                pass
            self.sock = None

    def _fail(self, now):
        self.close()
        self.failures += 1
        # 5 s, 10 s, 20 s ... capped at 5 minutes
        delay = min(300000, 5000 * (1 << min(self.failures - 1, 6)))
        self._next_try = time.ticks_add(now, delay)

    # ------------------------------------------------------------ reading

    def poll(self, now):
        """Read whatever has arrived. Never blocks. Call once per frame."""
        s = self.sock
        if s is None:
            return
        try:
            data = s.read(512)
        except OSError as e:
            if e.args and e.args[0] in (11, 110, -2):    # EAGAIN / timeout / WANT_READ
                data = None
            else:
                print("Inbox: connection error:", e)
                self._fail(now)
                return
        if data is None:
            if time.ticks_diff(now, self._last_rx) > STALE_MS:
                print("Inbox: stream went quiet, reconnecting")
                self._fail(now)
            return
        if not data:
            print("Inbox: server closed the stream")
            self._fail(now)
            return
        self._last_rx = now
        self.failures = 0
        self._raw += data
        try:
            self._parse()
        except ValueError as e:
            print("Inbox: bad response:", e)
            self._fail(now)

    def _parse(self):
        # _raw: bytes as received. _buf: the decoded body, split into lines.
        if self._state == "headers":
            end = self._raw.find(b"\r\n\r\n")
            if end < 0:
                if len(self._raw) > 4096:
                    raise ValueError("headers too long")
                return
            head = self._raw[:end].decode()
            self._raw = self._raw[end + 4:]
            status = head.split("\r\n", 1)[0]
            if " 200" not in status:
                raise ValueError(status)
            self._chunked = "chunked" in head.lower()
            self._state = "size" if self._chunked else "body"

        if self._chunked:
            self._dechunk()
        else:
            self._buf += self._raw
            self._raw = b""

        while True:
            nl = self._buf.find(b"\n")
            if nl < 0:
                if len(self._buf) > 8192:
                    raise ValueError("line too long")
                return
            line = self._buf[:nl].strip()
            self._buf = self._buf[nl + 1:]
            if line.startswith(b"{"):
                try:
                    self._event(json.loads(line))
                except ValueError:
                    pass

    def _dechunk(self):
        """Move complete chunk data from _raw to _buf ("size\r\ndata\r\n" framing)."""
        raw = self._raw
        while raw:
            if self._state == "size":
                nl = raw.find(b"\r\n")
                if nl < 0:
                    break
                size_txt = raw[:nl].split(b";")[0].strip()
                raw = raw[nl + 2:]
                if size_txt:           # blank line = the CRLF after a chunk's data
                    self._chunk_left = int(size_txt, 16)
                    if self._chunk_left == 0:
                        raise ValueError("stream ended")
                    self._state = "data"
            else:
                take = raw[:self._chunk_left]
                self._buf += take
                raw = raw[len(take):]
                self._chunk_left -= len(take)
                if self._chunk_left == 0:
                    self._state = "size"
        self._raw = raw

    # ------------------------------------------------------------ messages

    def _event(self, ev):
        if ev.get("event") != "message":
            return
        mid = ev.get("id", "")
        if mid in self._seen:
            return
        self._seen = (self._seen + [mid])[-6:]
        self._since = str(ev.get("time", ""))
        if self.store:
            now = time.ticks_ms()
            self.store.set("inbox.seen", ",".join(self._seen), "", now)
            self.store.set("inbox.since", self._since, "", now)

        body = to_ascii(ev.get("message", "") or "")
        title = to_ascii(ev.get("title", "") or "")
        msg = (title + ": " + body) if title and body else (title or body)
        msg = msg[:MAX_TEXT].strip()
        if not msg:
            return
        try:
            prio = int(ev.get("priority", 3))
        except (TypeError, ValueError):
            prio = 3
        seconds, color = STYLE.get(prio, STYLE[3])
        for tag in ev.get("tags", []) or []:
            if tag in COLORS:
                color = COLORS[tag]
        self.on_message(msg, seconds, color, prio >= 5)
