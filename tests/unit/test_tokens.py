"""SESS-02: link tokens carry 128 random bits and have a fixed URL-safe shape."""

import base64

from app.tokens import SESSION_ID_RE, new_session_id


def test_new_session_id_is_128_bit_url_safe_and_unique():
    samples = [new_session_id() for _ in range(1000)]
    assert len(set(samples)) == 1000
    for token in samples:
        assert SESSION_ID_RE.fullmatch(token)
        assert len(token) == 22
        assert len(base64.urlsafe_b64decode(token + "==")) == 16


def test_session_id_re_bounds():
    assert SESSION_ID_RE.fullmatch("a" * 22)
    assert SESSION_ID_RE.fullmatch("a" * 64)
    assert not SESSION_ID_RE.fullmatch("short")
    assert not SESSION_ID_RE.fullmatch("a" * 65)
    assert not SESSION_ID_RE.fullmatch("bad!chars_____________")
