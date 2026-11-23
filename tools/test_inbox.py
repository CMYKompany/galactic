"""Tests for device/inbox.py (ntfy message stream) against fake connections.

    python3 tools/test_inbox.py
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "mock"), os.path.join(os.path.dirname(HERE), "device")]

from sim import SIM, install_time  # noqa: E402

install_time()
import inbox  # noqa: E402


class FakeStream:
    """A non-blocking socket that releases scripted bytes at scripted times."""

    def __init__(self, script, eof_at=None, error_at=None):
        self.script = list(script)      # [(ms, bytes)]
        self.eof_at = eof_at
        self.error_at = error_at
        self.sent = b""
        self.closed = False

    def write(self, b):
        self.sent += b

    def setblocking(self, flag):
        assert flag is False

    def read(self, n):
        if self.error_at is not None and SIM.ms >= self.error_at:
            raise OSError(104)                      # ECONNRESET
        if self.script and SIM.ms >= self.script[0][0]:
            at, data = self.script.pop(0)
            if len(data) > n:
                self.script.insert(0, (at, data[n:]))
                data = data[:n]
            return data
        if self.eof_at is not None and SIM.ms >= self.eof_at and not self.script:
            return b""
        if self.script == [] and self.eof_at is None and SIM.ms % 7 == 0:
            raise OSError(11)                       # EAGAIN, as some ports do
        return None

    def close(self):
        self.closed = True


class Store:
    def __init__(self):
        self.d = {}

    def get(self, k, default):
        return self.d.get(k, default)

    def set(self, k, v, default, now):
        self.d[k] = v


def msg(mid, text, t=1700000000, **kw):
    ev = {"id": mid, "time": t, "event": "message", "topic": "x", "message": text}
    ev.update(kw)
    return (json.dumps(ev) + "\n").encode()


HEAD = b"HTTP/1.0 200 OK\r\nContent-Type: application/x-ndjson\r\n\r\n"
OPEN = b'{"id":"o1","time":1700000000,"event":"open","topic":"x"}\n'
KEEP = b'{"id":"k1","time":1700000045,"event":"keepalive","topic":"x"}\n'


def make(streams, store=None):
    got = []
    opened = []

    def opener(host, port, tls):
        opened.append((host, port, tls))
        return streams.pop(0)

    box = inbox.Inbox("https://ntfy.sh", "secret-topic",
                      lambda m, s, c, u: got.append((m, s, c, u)), store, opener)
    return box, got, opened


def run_for(box, ms, step=33):
    end = SIM.ms + ms
    while SIM.ms < end:
        if box.wants_connect(SIM.ms):
            box.connect(SIM.ms)
        box.poll(SIM.ms)
        SIM.ms += step


# ------------------------------------------------------------------ tests

def test_plain_stream_split_anywhere():
    SIM.__init__()
    body = HEAD + OPEN + msg("a1", "Lunch is here") + KEEP + msg("a2", "Second one")
    # deliver in awkward 7-byte pieces
    script = [(100 + i * 10, body[i:i + 7]) for i in range(0, len(body), 7)]
    box, got, opened = make([FakeStream(script)])
    run_for(box, 5000)
    assert [g[0] for g in got] == ["Lunch is here", "Second one"], got
    assert opened == [("ntfy.sh", 443, True)]
    print("ok  messages arrive intact however the stream is split")


def test_chunked_stream():
    SIM.__init__()
    payload = OPEN + msg("c1", "Chunked hello") + msg("c2", "And again")
    chunked = b""
    for i in range(0, len(payload), 13):          # chunk boundaries mid-line
        part = payload[i:i + 13]
        chunked += b"%x\r\n" % len(part) + part + b"\r\n"
    body = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + chunked
    script = [(100 + i * 10, body[i:i + 5]) for i in range(0, len(body), 5)]
    box, got, _ = make([FakeStream(script)])
    run_for(box, 5000)
    assert [g[0] for g in got] == ["Chunked hello", "And again"], got
    print("ok  chunked transfer encoding is decoded")


def test_request_and_since_on_reconnect():
    SIM.__init__()
    store = Store()
    s1 = FakeStream([(50, HEAD + OPEN + msg("r1", "one", t=1700000123))], eof_at=400)
    s2 = FakeStream([(9000, HEAD + OPEN + msg("r1", "one", t=1700000123)
                      + msg("r2", "two", t=1700000200))])
    box, got, opened = make([s1, s2], store)
    run_for(box, 12000)
    assert b"GET /secret-topic/json HTTP/1.0\r\n" in s1.sent, s1.sent
    assert b"GET /secret-topic/json?since=1700000123 HTTP/1.0" in s2.sent, s2.sent
    assert [g[0] for g in got] == ["one", "two"], got      # r1 not repeated
    assert len(opened) == 2
    # a fresh Inbox (board restarted) remembers what it has seen
    s3 = FakeStream([(13000, HEAD + msg("r2", "two", t=1700000200))])
    box2, got2, _ = make([s3], store)
    run_for(box2, 2000)
    assert got2 == [] and b"since=1700000200" in s3.sent, (got2, s3.sent)
    print("ok  reconnects resume after the last message; no repeats, even after restart")


def test_priority_tags_and_text_cleanup():
    SIM.__init__()
    body = HEAD + (msg("p1", "Low", priority=2)
                   + msg("p2", "Deploy finished", title="Build", priority=4)
                   + msg("p3", "Server down", priority=5)
                   + msg("p4", "Go", tags=["green", "rocket"])
                   + msg("p5", "It’s “done” — café ☕\nnext line"))
    box, got, _ = make([FakeStream([(10, body)])])
    run_for(box, 2000)
    assert got[0] == ("Low", 4, (200, 190, 175), False), got[0]
    assert got[1] == ("Build: Deploy finished", 10, (255, 180, 70), False), got[1]
    assert got[2] == ("Server down", 15, (255, 70, 60), True), got[2]
    assert got[3][2] == (110, 255, 140) and got[3][1] == 6, got[3]
    assert got[4][0] == "It's \"done\" - caf? ? next line", got[4]
    print("ok  priority sets duration/colour/urgency; colour tags; unicode made displayable")


def test_errors_back_off_and_recover():
    SIM.__init__()
    bad = FakeStream([(10, b"HTTP/1.1 404 Not Found\r\n\r\n")])
    reset = FakeStream([(10, HEAD + OPEN)], error_at=2000)
    quiet = FakeStream([(10, HEAD + OPEN)])                    # then silence
    good = FakeStream([(10, HEAD + msg("e1", "back"))])

    def failing(host, port, tls):
        raise OSError("DNS failed")

    streams = [bad, reset, quiet, good]
    got = []
    calls = []

    def opener(host, port, tls):
        calls.append(SIM.ms)
        if len(calls) == 1:
            return failing(host, port, tls)
        return streams.pop(0)

    box = inbox.Inbox("https://ntfy.sh", "t", lambda *a: got.append(a), None, opener)
    run_for(box, 400000, step=100)
    assert bad.closed and reset.closed and quiet.closed
    assert [g[0] for g in got] == ["back"], got
    gaps = [b - a for a, b in zip(calls, calls[1:])]
    assert gaps[0] >= 5000 and gaps[1] >= 5000, gaps            # backs off after failures
    assert any(g >= 120000 for g in gaps), gaps                 # quiet stream detected
    print("ok  DNS failure, HTTP error, reset and silent stream all recover")


def test_disabled_without_topic():
    box = inbox.Inbox("https://ntfy.sh", "", lambda *a: None)
    assert not box.enabled and not box.wants_connect(0)
    b2 = inbox.Inbox("http://192.168.1.20:8080", "t", lambda *a: None)
    assert (b2.host, b2.port, b2.use_tls) == ("192.168.1.20", 8080, False)
    print("ok  no topic = off; plain-http self-hosted server parsed")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL", t.__name__)
            traceback.print_exc()
    print("{} passed, {} failed".format(len(tests) - failed, failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
