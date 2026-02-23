import gzip
import json
import zlib

import pytest

from sec_financials import SecClient


class FakeResponse:
    def __init__(self, payload: bytes, content_encoding=None):
        self._payload = payload
        self.headers = {}
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _sample_json_bytes():
    return json.dumps({"ok": True, "n": 1}).encode("utf-8")


def test_get_json_decompresses_gzip_header(monkeypatch, tmp_path):
    raw = _sample_json_bytes()
    gz = gzip.compress(raw)

    def fake_urlopen(req, timeout=30):
        return FakeResponse(gz, content_encoding="gzip")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = SecClient(user_agent="Test UA", cache_dir=str(tmp_path))
    data = client.get_json("https://example.com/gzip.json", use_cache=False)

    assert data == {"ok": True, "n": 1}


def test_get_json_decompresses_deflate_header(monkeypatch, tmp_path):
    raw = _sample_json_bytes()
    df = zlib.compress(raw)

    def fake_urlopen(req, timeout=30):
        return FakeResponse(df, content_encoding="deflate")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = SecClient(user_agent="Test UA", cache_dir=str(tmp_path))
    data = client.get_json("https://example.com/deflate.json", use_cache=False)

    assert data == {"ok": True, "n": 1}


def test_get_json_detects_gzip_magic_without_header(monkeypatch, tmp_path):
    raw = _sample_json_bytes()
    gz = gzip.compress(raw)

    def fake_urlopen(req, timeout=30):
        return FakeResponse(gz)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = SecClient(user_agent="Test UA", cache_dir=str(tmp_path))
    data = client.get_json("https://example.com/no-header.json", use_cache=False)

    assert data == {"ok": True, "n": 1}


def test_get_json_reads_legacy_gzip_cache(tmp_path, monkeypatch):
    client = SecClient(user_agent="Test UA", cache_dir=str(tmp_path))
    url = "https://example.com/cached.json"
    cp = client._cache_path(url)
    cp.write_bytes(gzip.compress(_sample_json_bytes()))

    def should_not_call(*args, **kwargs):
        raise AssertionError("network should not be called when using cache")

    monkeypatch.setattr("urllib.request.urlopen", should_not_call)

    data = client.get_json(url, use_cache=True)

    assert data == {"ok": True, "n": 1}
