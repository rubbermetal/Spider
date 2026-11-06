import pytest
from spiderlib import db, queue, crawler
from spiderlib.fetch import HostThrottle

def get_url(conn, url):
    return conn.execute("SELECT * FROM urls WHERE url = ?", (url,)).fetchone()

def get_urls(conn):
    return conn.execute("SELECT * FROM urls").fetchall()

def page(links=(), title="T", extra_head=""):
    return f"""
    <html>
    <head>
        {extra_head}
        <title>{title}</title>
    </head>
    <body>
        {''.join(f'<a href="{link}">{link}</a>' for link in links)}
    </body>
    </html>
    """

def ok(body, url, **kw):
    result = {
        "ok": True,
        "status": 200,
        "final_url": url,
        "content_type": "text/html",
        "body": body.encode(),
        "truncated": False,
        "elapsed_ms": 5,
        "error": None,
        "error_kind": None,
        "skipped_reason": None
    }
    result.update(kw)
    return result

robots_ok = lambda url, ua, timeout: (404, "")

def claim(conn, url, seed=True):
    if seed:
        queue.add_seed(conn, url)
    else:
        queue.enqueue(conn, url)
    return queue.claim_next(conn)

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

S = dict(db.DEFAULT_SETTINGS, default_delay=0.0)

@pytest.fixture
def throttle():
    return HostThrottle(clock=lambda: 0.0, sleep=lambda s: None)

def test_success_stores_page_and_links(conn, throttle):
    seed_url = "http://a.com/"
    fetcher = lambda url, settings: ok(page(["/p1", "/p2"], title="Home"), url)
    result = crawler.process_one(conn, claim(conn, seed_url), S, throttle, fetcher, robots_ok)
    assert result == "done"
    row = get_url(conn, seed_url)
    assert row["status"] == "done"
    assert row["title"] == "Home"
    assert row["http_status"] == 200
    assert row["content_hash"] is not None
    for link in ["/p1", "/p2"]:
        row = get_url(conn, "http://a.com" + link)
        assert row["status"] == "queued"
        assert row["depth"] == 1

def test_nofollow_does_not_enqueue(conn, throttle):
    fetcher = lambda url, settings: ok(page(links=["/p1"], extra_head='<meta name="robots" content="nofollow">'), url)
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result == "done"
    row = get_url(conn, "http://a.com/p1")
    assert row is None

def test_noindex_hides(conn, throttle):
    fetcher = lambda url, settings: ok(page(extra_head='<meta name="robots" content="noindex">'), url)
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result == "done"
    row = get_url(conn, "http://a.com/")
    assert row["hidden"] == 1

def test_failure_retries(conn, throttle):
    fetcher = lambda url, settings: {
        "ok": False,
        "status": None,
        "final_url": url,
        "content_type": "",
        "body": b"",
        "truncated": False,
        "elapsed_ms": 1,
        "error": "timed out",
        "error_kind": "timeout",
        "skipped_reason": None
    }
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result == "queued"
    fetcher = lambda url, settings: {
        "ok": False,
        "status": 404,
        "final_url": url,
        "content_type": "",
        "body": b"",
        "truncated": False,
        "elapsed_ms": 1,
        "error": "HTTP error",
        "error_kind": "http",
        "skipped_reason": None
    }
    result = crawler.process_one(conn, claim(conn, "http://b.com/"), S, throttle, fetcher, robots_ok)
    assert result == "error"

def test_non_html_marked_done_without_parse(conn, throttle):
    fetcher = lambda url, settings: ok("", url, skipped_reason="content-type", content_type="application/pdf")
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result == "done"
    row = get_url(conn, "http://a.com/")
    assert row["title"] is None
    assert len(get_urls(conn)) == 1

def test_robots_disallow_blocks(conn, throttle):
    robots_fetcher = lambda url, ua, timeout: (200, "User-agent: *\nDisallow: /")
    fetcher = lambda url, settings: AssertionError("fetcher should not be called")
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_fetcher)
    assert result == "blocked"
    row = get_url(conn, "http://a.com/")
    assert row["error"] == "robots.txt"

def test_robots_ignored_when_switch_off(conn, throttle):
    robots_fetcher = lambda url, ua, timeout: (200, "User-agent: *\nDisallow: /")
    fetcher = lambda url, settings: ok(page(), url)
    settings = dict(S, respect_robots=False)
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), settings, throttle, fetcher, robots_fetcher)
    assert result == "done"

def test_blocked_domain(conn, throttle):
    conn.execute("INSERT INTO domains (host, blocked) VALUES ('a.com', 1)")
    conn.commit()
    fetcher = lambda url, settings: AssertionError("fetcher should not be called")
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result == "blocked"
    row = get_url(conn, "http://a.com/")
    assert row["error"] == "domain blocked"

def test_redirect_out_of_scope_skipped(conn, throttle):
    fetcher = lambda url, settings: ok(page(), "http://other.org/x")
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result == "skipped"
    row = get_url(conn, "http://a.com/")
    assert row["error"] == "redirect out of scope"
    fetcher = lambda url, settings: ok(page(), "http://www.c.com/")
    result = crawler.process_one(conn, claim(conn, "http://c.com/"), S, throttle, fetcher, robots_ok)
    assert result == "done"

def test_exception_is_contained(conn, throttle):
    def fetcher(url, settings):
        raise RuntimeError("boom")
    result = crawler.process_one(conn, claim(conn, "http://a.com/"), S, throttle, fetcher, robots_ok)
    assert result in ("queued", "error")
    messages = [r["message"] for r in conn.execute("SELECT message FROM log WHERE level = 'error'")]
    assert any("boom" in m for m in messages)

class ThrottleRecorder:
    def __init__(self):
        self.calls = []

    def wait(self, host, delay):
        self.calls.append((host, delay))

def test_throttle_called_with_host_and_delay(conn, throttle):
    settings = dict(S, default_delay=1.5)
    recorder = ThrottleRecorder()
    throttle = recorder
    fetcher = lambda url, settings: ok(page(), url)
    crawler.process_one(conn, claim(conn, "http://a.com/"), settings, throttle, fetcher, robots_ok)
    assert recorder.calls == [("a.com", 1.5)]
