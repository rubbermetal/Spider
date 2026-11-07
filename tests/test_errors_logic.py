import pytest
from spiderlib.admin import errors_logic as el

def test_classify_blocked_and_skipped():
    assert el.classify("blocked", None, "robots.txt") == "blocked-robots"
    assert el.classify("blocked", None, "domain blocked") == "blocked-domain"
    assert el.classify("skipped", None, "redirect out of scope") == "skipped-redirect"
    assert el.classify("blocked", None, None) == "blocked-robots"

def test_classify_http():
    assert el.classify("error", 404, "HTTP 404") == "http-404"
    assert el.classify("error", 503, "HTTP 503") == "http-503"
    assert el.classify("error", 500, None) == "http-500"
    assert el.classify("error", 302, "too many redirects") == "redirects"

@pytest.mark.parametrize("error_text, expected", [
    ("timed out", "timeout"),
    ("The read operation TIMEOUT", "timeout"),
    ("[Errno -2] Name or service not known", "dns"),
    ("getaddrinfo failed", "dns"),
    ("Temporary failure in name resolution", "dns"),
    ("[SSL: CERTIFICATE_VERIFY_FAILED] bad", "ssl"),
    ("certificate has expired", "ssl"),
    ("too many redirects", "redirects"),
    ("[Errno 111] Connection refused", "connection"),
    ("Connection reset by peer", "connection"),
    ("Network is unreachable", "connection"),
    ("bad gzip data", "other"),
    ("", "other"),
    (None, "other"),
])
def test_classify_text(error_text, expected):
    assert el.classify("error", None, error_text) == expected

def test_label():
    assert el.label("blocked-robots") == "Blocked by robots.txt"
    assert el.label("timeout") == "Timeouts"
    assert el.label("dns") == "DNS failures"
    assert el.label("ssl") == "SSL / certificate errors"
    assert el.label("http-404") == "HTTP 404"
    assert el.label("http-503") == "HTTP 503"
    assert el.label("something-else") == "something-else"
    assert el.label("other") == "Other errors"

def test_is_valid_kind():
    for kind in el.FIXED_KINDS:
        assert el.is_valid_kind(kind)
    assert el.is_valid_kind("http-404")
    assert el.is_valid_kind("http-500")
    assert not el.is_valid_kind("")
    assert not el.is_valid_kind("http-40")
    assert not el.is_valid_kind("http-4040")
    assert not el.is_valid_kind("http-abc")
    assert not el.is_valid_kind("../etc")
    assert not el.is_valid_kind("HTTP-404")
    assert not el.is_valid_kind("nope")

def test_fixed_kinds_are_labelled():
    for kind in el.FIXED_KINDS:
        assert el.label(kind) != kind
