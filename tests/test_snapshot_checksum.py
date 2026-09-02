"""The baked snapshot is checksum-verified on download.

`ensure_db` has always accepted a `sha256`, but nothing passed one, so the
only integrity check on the release asset was the gzip magic number — a
truncated download passes that. These tests pin the digest to the declared
URL and prove the wiring reaches `ensure_db`, because the failure mode of
getting this wrong is silent: a corrupt snapshot caches and is trusted forever.
"""
import gzip
import hashlib
import re

import pytest

from eyecore import BaseDB
from esoterica._query import _BASE, _DATA_SHA256, _DATA_URL


def test_digest_is_a_sha256_hex_string():
    assert re.fullmatch(r"[0-9a-f]{64}", _DATA_SHA256)


def test_digest_is_wired_through_to_the_download():
    assert _BASE._remote_url == _DATA_URL
    assert _BASE._remote_sha256 == _DATA_SHA256


def _serve(monkeypatch, payload: bytes) -> None:
    class FakeResponse:
        def __init__(self):
            self._data = payload
        def read(self, n=-1):
            d, self._data = self._data, b""
            return d
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: FakeResponse())


def test_a_substituted_snapshot_is_rejected_and_not_cached(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    _serve(monkeypatch, gzip.compress(b"not the real snapshot"))

    gz = tmp_path / "_data" / "esoterica.db.gz"
    db = BaseDB("esoterica-test", gz_path=gz, remote_url=_DATA_URL,
                remote_sha256=_DATA_SHA256)
    with pytest.raises(OSError, match="Checksum mismatch"):
        db.conn
    assert not gz.exists()


def test_a_matching_snapshot_is_accepted(tmp_path, monkeypatch):
    payload = gzip.compress(b"stand-in snapshot bytes")
    _serve(monkeypatch, payload)

    from eyecore._remote_data import ensure_db

    gz = tmp_path / "_data" / "esoterica.db.gz"
    out = ensure_db("esoterica-test", _DATA_URL, gz,
                    hashlib.sha256(payload).hexdigest())
    assert out.read_bytes() == payload
