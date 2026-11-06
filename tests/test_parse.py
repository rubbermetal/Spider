import pytest
from spiderlib.parse import parse_html, decode_body, content_hash

page_url = "http://example.com/dir/page"

def test_title_and_description():
    html = '<html><head><title>  Hello \n World </title><meta name="Description" content="  A  test   page "></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['title'] == "Hello World"
    assert result['description'] == "A test page"

def test_og_fallbacks():
    html = '<html><head><meta property="og:title" content="OG T"><meta property="og:description" content="OG D"></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['title'] == "OG T"
    assert result['description'] == "OG D"

def test_no_metadata():
    html = "<p>hi</p>"
    result = parse_html(html, page_url)
    assert result['title'] == ""
    assert result['description'] == ""
    assert result['canonical'] is None
    assert result['noindex'] is False
    assert result['nofollow'] is False
    assert result['links'] == []

def test_canonical():
    html = '<html><head><link rel="Canonical" href="/canon?utm_source=x"></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['canonical'] == "http://example.com/canon"

def test_robots_meta():
    html = '<html><head><meta name="ROBOTS" content="NoIndex, follow"></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['noindex'] is True
    assert result['nofollow'] is False

    html = '<html><head><meta name="ROBOTS" content="nofollow"></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['noindex'] is False
    assert result['nofollow'] is True

    html = '<html><head><meta name="ROBOTS" content="none"></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['noindex'] is True
    assert result['nofollow'] is True

    html = '<html><head><meta name="ROBOTS" content="noindex"><meta name="ROBOTS" content="nofollow"></head><body>x</body></html>'
    result = parse_html(html, page_url)
    assert result['noindex'] is True
    assert result['nofollow'] is True

def test_links_resolved_and_filtered():
    html = '<html><body><a href="/a">1</a><a href="b">2</a><a href="http://other.org/x#f">3</a><a href="mailto:x@y.z">4</a><a href="javascript:void(0)">5</a><a href="#top">6</a><a href="/a">7</a><a href="/dir/page">8</a><a href="ftp://x/y">9</a><a>10</a></body></html>'
    result = parse_html(html, page_url)
    assert result['links'] == ["http://example.com/a", "http://example.com/dir/b", "http://other.org/x"]

def test_base_tag():
    html = '<html><head><base href="http://cdn.example.net/root/"></head><body><a href="x">1</a></body></html>'
    result = parse_html(html, page_url)
    assert result['links'] == ["http://cdn.example.net/root/x"]

def test_max_links():
    html = '<html><body>' + ''.join(f'<a href="/p{i}">link{i}</a>' for i in range(1500)) + '</body></html>'
    result = parse_html(html, page_url)
    assert len(result['links']) == 1000
    assert result['links'][0] == "http://example.com/p0"

def test_text_extraction():
    html = '<html><head><title>T</title><style>p{color:red}</style></head><body><p>Hello</p><script>var x = 1;</script><p>World <b>again</b></p><noscript>nojs</noscript></body></html>'
    result = parse_html(html, page_url)
    assert result['text'] == "Hello World again"

def test_text_truncated():
    html = '<p>' + 'a' * 6000 + '</p>'
    result = parse_html(html, page_url)
    assert len(result['text']) == 5000

def test_title_truncated():
    html = '<title>' + 'x' * 400 + '</title>'
    result = parse_html(html, page_url)
    assert len(result['title']) == 300

def test_broken_html_does_not_raise():
    html = '<div><a href="/ok">x</div></span><title>'
    result = parse_html(html, page_url)
    assert 'links' in result

def test_decode_header_charset():
    assert decode_body("café".encode("latin-1"), "text/html; charset=ISO-8859-1") == "café"

def test_decode_meta_charset():
    body = b'<meta charset="iso-8859-1"><p>caf\xe9</p>'
    assert "café" in decode_body(body, None)

def test_decode_default_utf8_and_bad_bytes():
    assert decode_body("héllo".encode("utf-8")) == "héllo"
    assert decode_body(b"abc\xff\xfe").startswith("abc")

def test_decode_unknown_charset_falls_back():
    assert decode_body(b"abc", "text/html; charset=nonsense-xyz") == "abc"

def test_content_hash():
    assert content_hash("a") == "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"
    assert content_hash("a") != content_hash("b")
