import pytest

from api_app import _safe_session_id


def test_safe_session_id_basic():
    assert _safe_session_id("abcDEF_123-xyz") == "abcDEF_123-xyz"


def test_safe_session_id_sanitizes():
    sid = _safe_session_id("../../etc/passwd")
    assert "/" not in sid and "\\" not in sid and "." not in sid
    assert sid.endswith("etc_passwd")


def test_safe_session_id_empty_raises():
    with pytest.raises(ValueError):
        _safe_session_id("   ")

