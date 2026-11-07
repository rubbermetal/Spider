import threading
import time
import pytest
from spiderlib import crawler, db

FETCHED = []

def fake_fetch(url, settings):
    FETCHED.append(url)
    return {
        "ok": True,
        "status": 200,
        "final_url": url,
        "content_type": "text/html",
        "body": b"<html><title>T</title></html>",
        "truncated": False,
        "elapsed_ms": 1,
        "error": None,
        "error_kind": None,
        "skipped_reason": None
    }

def robots_none(url, ua, timeout):
    return (404, "")

def wait_for(cond, timeout=8.0):
    start = time.time()
    while not cond():
        if time.time() - start > timeout:
            return cond()
        time.sleep(0.02)
    return cond()

def make(dbpath, hours):
    conn = db.connect(dbpath)
    db.set_setting(conn, "default_delay", 0.0)
    db.set_setting(conn, "concurrency", 1)
    conn.execute("INSERT INTO seeds (url, recrawl_hours, last_crawled, added_at) VALUES ('http://a.com/', ?, '2000-01-01T00:00:00Z', '2000-01-01T00:00:00Z')", (hours,))
    conn.execute("INSERT INTO urls (url, seed_id, status, added_at, host) VALUES ('http://a.com/', 1, 'done', ?, 'a.com')", (db.now(),))
    conn.commit()
    return conn

@pytest.fixture
def dbpath(tmp_path):
    return str(tmp_path / "t.db")

def test_keep_running_recrawls_due_seed(dbpath):
    FETCHED.clear()
    conn = make(dbpath, 1)
    c = crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01)
    c.schedule_interval = 0.05
    thread = threading.Thread(target=c.run, args=(False,), daemon=True)
    thread.start()
    assert wait_for(lambda: "http://a.com/" in FETCHED)
    crawler.request_stop(conn)
    thread.join(timeout=8)
    assert not thread.is_alive()
    seed = conn.execute("SELECT * FROM seeds WHERE id = 1").fetchone()
    assert seed['last_crawled'] != "2000-01-01T00:00:00Z"
    url = conn.execute("SELECT * FROM urls WHERE url = 'http://a.com/'").fetchone()
    assert url['status'] == "done"
    logs = conn.execute("SELECT message FROM log").fetchall()
    assert any(log['message'].startswith("scheduled recrawl") for log in logs)

def test_one_shot_run_does_not_schedule(dbpath):
    FETCHED.clear()
    conn = make(dbpath, 1)
    crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01).run()
    assert FETCHED == []
    seed = conn.execute("SELECT * FROM seeds WHERE id = 1").fetchone()
    assert seed['last_crawled'] == "2000-01-01T00:00:00Z"

def test_not_due_seed_is_left_alone(dbpath):
    FETCHED.clear()
    conn = make(dbpath, 1)
    conn.execute("UPDATE seeds SET last_crawled = ? WHERE id = 1", (db.now(),))
    conn.commit()
    c = crawler.Crawler(dbpath, fake_fetch, robots_none, idle_sleep=0.01)
    c.schedule_interval = 0.05
    thread = threading.Thread(target=c.run, args=(False,), daemon=True)
    thread.start()
    time.sleep(0.5)
    crawler.request_stop(conn)
    thread.join(timeout=8)
    assert FETCHED == []
