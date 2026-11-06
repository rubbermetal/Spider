import pytest
import threading
import time
from spiderlib import db, queue, crawler

SITE = {
    "http://a.com/": '<html><title>Home</title><a href="/p1">1</a><a href="/p2">2</a></html>',
    "http://a.com/p1": '<html><title>P1</title><a href="/p3">3</a><a href="/">home</a></html>',
    "http://a.com/p2": '<html><title>P2</title></html>',
    "http://a.com/p3": '<html><title>P3</title><a href="/p4">4</a></html>',
    "http://a.com/p4": '<html><title>P4</title></html>'
}

FETCHED = []

def fake_fetch(url, settings):
    global FETCHED
    FETCHED.append(url)
    if url in SITE:
        return {
            "ok": True,
            "status": 200,
            "final_url": url,
            "content_type": "text/html",
            "body": SITE[url].encode(),
            "truncated": False,
            "elapsed_ms": 1,
            "error": None,
            "error_kind": None,
            "skipped_reason": None
        }
    else:
        return {
            "ok": False,
            "status": 404,
            "final_url": url,
            "content_type": "",
            "body": b"",
            "truncated": False,
            "elapsed_ms": 1,
            "error": "HTTP 404",
            "error_kind": "http",
            "skipped_reason": None
        }

def robots_none(url, ua, timeout):
    return (404, "")

def make(dbpath, concurrency=2, **settings):
    conn = db.connect(dbpath)
    db.set_setting(conn, "default_delay", 0.0)
    db.set_setting(conn, "concurrency", concurrency)
    for key, value in settings.items():
        db.set_setting(conn, key, value)
    return conn

def get_urls(conn):
    return [(r["url"], r["status"]) for r in conn.execute("SELECT url, status FROM urls")]

def get_setting(conn, key):
    return db.get_settings(conn)[key]

def get_log_messages(conn):
    return [r["message"] for r in conn.execute("SELECT message FROM log")]

def urls_by_status(conn):
    return {url: status for url, status in get_urls(conn)}

@pytest.fixture
def dbpath(tmp_path):
    return str(tmp_path / "t.db")

def test_crawls_whole_site(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath)
    queue.add_seed(conn, "http://a.com/", max_depth=5)
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01).run()
    urls_status = urls_by_status(conn)
    assert all(status == "done" for status in urls_status.values())
    assert set(FETCHED) == set(SITE)
    assert len(FETCHED) == 5
    assert get_setting(conn, "crawl_state") == "stopped"

def test_depth_limit(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath)
    queue.add_seed(conn, "http://a.com/", max_depth=1)
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01).run()
    urls_status = urls_by_status(conn)
    assert urls_status.get("http://a.com/") == "done"
    assert urls_status.get("http://a.com/p1") == "done"
    assert urls_status.get("http://a.com/p2") == "done"
    assert "http://a.com/p3" not in urls_status
    assert "http://a.com/p4" not in urls_status

def test_stopped_state_prevents_work(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath)
    queue.add_seed(conn, "http://a.com/", max_depth=1)
    db.set_setting(conn, "crawl_state", "stopped")
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01)._worker()
    assert not FETCHED

def test_pause_then_resume(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath, concurrency=1)
    queue.add_seed(conn, "http://a.com/", max_depth=5)
    db.set_setting(conn, "crawl_state", "paused")
    thread = threading.Thread(target=crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01)._worker)
    thread.start()
    time.sleep(0.3)
    assert not FETCHED
    crawler.resume(conn)
    thread.join(timeout=10)
    assert len(FETCHED) == 5
    assert not thread.is_alive()

def test_resume_recovers_interrupted(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath)
    queue.add_seed(conn, "http://a.com/", max_depth=1)
    row = queue.claim_next(conn)
    db.set_setting(conn, "crawl_state", "running")
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01).run()
    urls_status = urls_by_status(conn)
    assert urls_status.get("http://a.com/") == "done"

def test_request_stop_function(dbpath):
    conn = make(dbpath)
    crawler.pause(conn)
    assert get_setting(conn, "crawl_state") == "paused"
    crawler.resume(conn)
    assert get_setting(conn, "crawl_state") == "running"
    crawler.request_stop(conn)
    assert get_setting(conn, "crawl_state") == "stopped"

def test_failed_urls_retry_then_error(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath, max_retries=0)
    queue.add_seed(conn, "http://a.com/missing", max_depth=1)
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01).run()
    urls_status = urls_by_status(conn)
    assert urls_status.get("http://a.com/missing") == "error"
    assert FETCHED == ["http://a.com/missing"]

def test_log_has_start_and_stop(dbpath):
    global FETCHED
    FETCHED = []
    conn = make(dbpath)
    queue.add_seed(conn, "http://a.com/", max_depth=1)
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01).run()
    log_messages = get_log_messages(conn)
    assert "crawl started" in log_messages
    assert "crawl stopped" in log_messages
