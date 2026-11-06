import pytest
from datetime import datetime, timedelta, timezone
from spiderlib import db, robots

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def make_fetcher(status, text):
    def fetcher(url, ua, timeout):
        fetcher.calls.append(url)
        return status, text
    fetcher.calls = []
    return fetcher

S = dict(db.DEFAULT_SETTINGS)

def test_disallow_path(conn):
    f = make_fetcher(200, "User-agent: *\nDisallow: /private/")
    assert not robots.allowed(conn, "http://a.com/private/x", S, f)
    assert robots.allowed(conn, "http://a.com/public", S, f)

def test_specific_agent_blocked(conn):
    f = make_fetcher(200, "User-agent: SpiderBot\nDisallow: /")
    assert not robots.allowed(conn, "http://a.com/", S, f)

def test_other_agent_rule_ignored(conn):
    f = make_fetcher(200, "User-agent: SomeoneElse\nDisallow: /")
    assert robots.allowed(conn, "http://a.com/", S, f)

@pytest.mark.parametrize("status, expected", [
    (404, True),
    (410, True),
    (403, False),
    (401, False),
    (500, False),
    (503, False),
    (None, False),
])
def test_status_policies(conn, status, expected):
    f = make_fetcher(status, "")
    assert robots.allowed(conn, "http://a.com/x", S, f) == expected

def test_ignore_switch(conn):
    S_no_robots = dict(S, respect_robots=False)
    f = make_fetcher(200, "User-agent: *\nDisallow: /")
    assert robots.allowed(conn, "http://a.com/", S_no_robots, f)
    assert not f.calls
    assert conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0] == 0

def test_fetched_url_and_cache(conn):
    f = make_fetcher(200, "User-agent: *\nAllow: /")
    assert robots.allowed(conn, "https://a.com/page", S, f)
    assert robots.allowed(conn, "https://a.com/page", S, f)
    assert f.calls == ["https://a.com/robots.txt"]
    assert conn.execute("SELECT robots_status FROM domains WHERE host='a.com'").fetchone()[0] == 200

def test_stale_cache_refetches(conn):
    f = make_fetcher(200, "User-agent: *\nAllow: /")
    assert robots.allowed(conn, "http://a.com/", S, f)
    now = datetime.now(timezone.utc)
    conn.execute("UPDATE domains SET robots_fetched_at = ? WHERE host='a.com'", [(now - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")])
    assert robots.allowed(conn, "http://a.com/", S, f)
    assert len(f.calls) == 2

def test_good_cache_not_refetched_after_2_hours(conn):
    f = make_fetcher(200, "User-agent: *\nAllow: /")
    assert robots.allowed(conn, "http://a.com/", S, f)
    now = datetime.now(timezone.utc)
    conn.execute("UPDATE domains SET robots_fetched_at = ? WHERE host='a.com'", [(now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")])
    assert robots.allowed(conn, "http://a.com/", S, f)
    assert len(f.calls) == 1

def test_failed_cache_retried_after_2_hours(conn):
    f = make_fetcher(500, "")
    assert not robots.allowed(conn, "http://a.com/", S, f)
    now = datetime.now(timezone.utc)
    conn.execute("UPDATE domains SET robots_fetched_at = ? WHERE host='a.com'", [(now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")])
    assert not robots.allowed(conn, "http://a.com/", S, f)
    assert len(f.calls) == 2

def test_crawl_delay_from_robots(conn):
    f = make_fetcher(200, "User-agent: *\nCrawl-delay: 10")
    assert robots.crawl_delay(conn, "http://a.com/", S, f) == 10.0

def test_crawl_delay_default(conn):
    f = make_fetcher(200, "User-agent: *\nDisallow: /x")
    assert robots.crawl_delay(conn, "http://a.com/", S, f) == 2.0

def test_crawl_delay_robots_smaller_than_default(conn):
    f = make_fetcher(200, "User-agent: *\nCrawl-delay: 1")
    assert robots.crawl_delay(conn, "http://a.com/", S, f) == 2.0

def test_crawl_delay_override_wins(conn):
    f = make_fetcher(200, "User-agent: *\nCrawl-delay: 10")
    assert robots.allowed(conn, "http://a.com/", S, f)
    conn.execute("UPDATE domains SET delay_override = 0.5 WHERE host='a.com'")
    assert robots.crawl_delay(conn, "http://a.com/", S, f) == 0.5

def test_crawl_delay_ignores_robots_when_switch_off(conn):
    S_no_robots = dict(S, respect_robots=False)
    f = make_fetcher(200, "User-agent: *\nCrawl-delay: 10")
    assert robots.crawl_delay(conn, "http://a.com/", S_no_robots, f) == 2.0

def test_fetch_robots_txt_never_raises():
    assert robots.fetch_robots_txt("http://127.0.0.1:1/robots.txt", "x", 1) == (None, "")
