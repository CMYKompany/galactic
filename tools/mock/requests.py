"""Mock of MicroPython's requests. By default there is no internet; tests can
install a fake server with serve(files)."""
_FILES = None   # {url_suffix: bytes} when a fake server is installed
calls = []


def serve(files):
    global _FILES
    _FILES = files


class _Raw:
    def __init__(self, data):
        self._data = data
        self._pos = 0

    def read(self, n=-1):
        if n < 0:
            n = len(self._data) - self._pos
        out = self._data[self._pos:self._pos + n]
        self._pos += len(out)
        return out

    def close(self):
        pass


class Response:
    def __init__(self, status, data):
        self.status_code = status
        self.raw = _Raw(data)

    @property
    def content(self):
        return self.raw.read()

    def json(self):
        import json
        return json.loads(self.content)

    def close(self):
        pass


def get(url, headers=None, timeout=None):
    calls.append(url)
    if _FILES is None:
        raise OSError("no network in simulator")
    path = url.split("?")[0]
    for suffix, data in _FILES.items():
        if path.endswith("/" + suffix):
            return Response(200, data)
    return Response(404, b"")
