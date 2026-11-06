from spiderlib.urls import *
import pytest

@pytest.mark.parametrize("url, base, expected", [
    ("HTTP://Example.COM/a", None, "http://example.com/a"),
    ("http://example.com", None, "http://example.com/"),
    ("https://example.com:443/x", None, "https://example.com/x"),
    ("http://example.com:80/x", None, "http://example.com/x"),
    ("http://example.com:8080/x", None, "http://example.com:8080/x"),
    ("http://user:pw@example.com/x", None, "http://example.com/x"),
    ("http://example.com/a#frag", None, "http://example.com/a"),
    ("http://example.com/a?b=2&a=1", None, "http://example.com/a?a=1&b=2"),
    ("http://example.com/a?utm_source=x&id=5&fbclid=z", None, "http://example.com/a?id=5"),
    ("http://example.com/a?utm_source=x", None, "http://example.com/a"),
    ("/other", "http://example.com/dir/page", "http://example.com/other"),
    ("page2", "http://example.com/dir/page", "http://example.com/dir/page2"),
    ("../up", "http://example.com/a/b/c", "http://example.com/a/up"),
    ("  http://example.com/  ", None, "http://example.com/"),
    ("http://example.com./x", None, "http://example.com/x"),
    ("http://example.com/dir/", None, "http://example.com/dir/"),
    ("mailto:a@b.com", None, None),
    ("javascript:void(0)", None, None),
    ("ftp://example.com/x", None, None),
    ("", None, None),
    ("http:///nohost", None, None),
    ("http://example.com/" + "a"*2100, None, None)
])
def test_normalize_url(url, base, expected):
    assert normalize_url(url, base) == expected

def test_host_of():
    assert host_of("http://Sub.Example.com:8080/x") == "sub.example.com"
    assert host_of("garbage") == ""

def test_registered_domain():
    assert registered_domain("www.blog.example.com") == "example.com"
    assert registered_domain("example.com") == "example.com"
    assert registered_domain("localhost") == "localhost"
    assert registered_domain("10.1.2.3") == "10.1.2.3"

def test_is_same_site():
    assert is_same_site("http://a.example.com/x", "https://b.example.com/y") is True
    assert is_same_site("http://example.com", "http://example.org") is False
    assert is_same_site("garbage", "garbage") is False

def test_has_skipped_extension():
    assert has_skipped_extension("http://x.com/pic.JPG?v=1") is True
    assert has_skipped_extension("http://x.com/page.html") is False
    assert has_skipped_extension("http://x.com/dir/") is False
    assert has_skipped_extension("http://x.com/a.pdf") is True
