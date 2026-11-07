"""Regression tests for 'database is locked' seen on a real crawl (2026-11-07).

Cause: robots.get_robots ran INSERT OR IGNORE (which opens a write transaction) and
returned from its cached path without committing, so a worker kept the SQLite write
lock through the per-host delay and the network fetch. The other workers then timed
out and, because the error handler itself wrote to the log, died.
"""
import sqlite3

import pytest

from spiderlib import crawler, db, queue, robots

SITE = {
    "http://a.com/": '<html><title>Home</title><a href="/p1">1</a><a href="/p2">2</a></html>',
    "http://a.com/p1": '<html><title>P1</title></html>',
    "http://a.com/p2": '<html><title>P2</title></html>',
}


def ok_page(url, body):
    return {"ok": True, "status": 200, "final_url": url, "content_type": "text/html",
            "body": body.encode(), "truncated": False, "elapsed_ms": 1, "error": None,
            "error_kind": None, "skipped_reason": None}


def robots_404(url, ua, timeout):
    return (404, "")


@pytest.fixture
def dbpath(tmp_path):
    return str(tmp_path / "t.db")


def probe_can_write(dbpath):
    """True when a second connection can write RIGHT NOW (no waiting)."""
    other = db.connect(dbpath)
    try:
        other.execute("PRAGMA busy_timeout=0")
        other.execute("INSERT INTO log (ts, level, message) VALUES ('t', 'info', 'probe')")
        other.commit()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        other.close()


# ---- robots.get_robots must not leave a transaction open --------------------- #

def test_get_robots_first_fetch_leaves_no_open_transaction(dbpath):
    conn = db.connect(dbpath)
    S = dict(db.DEFAULT_SETTINGS)
    robots.get_robots(conn, "http://a.com/x", S, robots_404)
    assert conn.in_transaction is False


def test_get_robots_cached_path_leaves_no_open_transaction(dbpath):
    conn = db.connect(dbpath)
    S = dict(db.DEFAULT_SETTINGS)
    robots.get_robots(conn, "http://a.com/x", S, robots_404)      # fills the cache
    robots.get_robots(conn, "http://a.com/y", S, robots_404)      # served from the cache
    assert conn.in_transaction is False


def test_allowed_and_crawl_delay_leave_no_open_transaction(dbpath):
    conn = db.connect(dbpath)
    S = dict(db.DEFAULT_SETTINGS)
    robots.allowed(conn, "http://a.com/x", S, robots_404)
    robots.allowed(conn, "http://a.com/y", S, robots_404)
    robots.crawl_delay(conn, "http://a.com/y", S, robots_404)
    assert conn.in_transaction is False


def test_other_connection_can_write_after_cached_get_robots(dbpath):
    conn = db.connect(dbpath)
    S = dict(db.DEFAULT_SETTINGS)
    robots.get_robots(conn, "http://a.com/x", S, robots_404)
    robots.get_robots(conn, "http://a.com/y", S, robots_404)
    assert probe_can_write(dbpath)


def test_new_host_row_is_still_created(dbpath):
    conn = db.connect(dbpath)
    S = dict(db.DEFAULT_SETTINGS)
    robots.get_robots(conn, "http://new.example/x", S, robots_404)
    row = conn.execute("SELECT robots_status FROM domains WHERE host = 'new.example'").fetchone()
    assert row is not None and row[0] == 404


# ---- the real invariant: no write lock during a fetch -------------------------- #

def test_no_write_lock_is_held_while_fetching_with_robots_respected(dbpath):
    conn = db.connect(dbpath)
    db.set_setting(conn, "default_delay", 0.0)
    db.set_setting(conn, "concurrency", 1)
    db.set_setting(conn, "respect_robots", True)
    queue.add_seed(conn, "http://a.com/", max_depth=3)
    probes = []

    def fetcher(url, settings):
        probes.append(probe_can_write(dbpath))
        return ok_page(url, SITE[url]) if url in SITE else {
            "ok": False, "status": 404, "final_url": url, "content_type": "", "body": b"",
            "truncated": False, "elapsed_ms": 1, "error": "HTTP 404", "error_kind": "http",
            "skipped_reason": None}

    crawler.Crawler(dbpath, fetcher, robots_404, idle_sleep=0.01).run()
    assert len(probes) == 3                       # the whole site was fetched
    assert all(probes), "a write lock was held while fetching: %r" % probes


def test_no_write_lock_is_held_while_fetching_with_robots_ignored(dbpath):
    conn = db.connect(dbpath)
    db.set_setting(conn, "default_delay", 0.0)
    db.set_setting(conn, "concurrency", 1)
    db.set_setting(conn, "respect_robots", False)
    queue.add_seed(conn, "http://a.com/", max_depth=3)
    probes = []

    def fetcher(url, settings):
        probes.append(probe_can_write(dbpath))
        return ok_page(url, SITE[url])

    crawler.Crawler(dbpath, fetcher, robots_404, idle_sleep=0.01).run()
    assert len(probes) == 3 and all(probes)


# ---- a failed log write must not kill a worker -------------------------------- #

def test_worker_survives_a_failing_log_write(dbpath, monkeypatch):
    conn = db.connect(dbpath)
    db.set_setting(conn, "concurrency", 1)
    db.set_setting(conn, "crawl_state", "running")    # a fresh db starts 'stopped'; the worker would exit at once

    def boom(c):
        db.set_setting(c, "crawl_state", "stopped")   # so the loop ends after the error
        raise RuntimeError("boom")

    def locked_log(c, level, message):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(queue, "claim_next", boom)
    monkeypatch.setattr(db, "log_event", locked_log)
    assert db.get_settings(conn)["crawl_state"] == "running"
    # must return normally instead of dying with the OperationalError from log_event
    crawler.Crawler(dbpath, lambda u, s: ok_page(u, SITE[u]), robots_404, idle_sleep=0.01)._worker()


def test_worker_rolls_back_an_open_transaction_after_an_error(dbpath, monkeypatch):
    conn = db.connect(dbpath)
    db.set_setting(conn, "concurrency", 1)
    db.set_setting(conn, "crawl_state", "running")    # a fresh db starts 'stopped'; the worker would exit at once
    seen = {}

    def boom(c):
        db.set_setting(c, "crawl_state", "stopped")
        c.execute("INSERT INTO log (ts, level, message) VALUES ('t', 'info', 'half done')")   # opens a txn
        seen["conn"] = c
        raise RuntimeError("boom")

    monkeypatch.setattr(queue, "claim_next", boom)
    crawler.Crawler(dbpath, lambda u, s: ok_page(u, SITE[u]), robots_404, idle_sleep=0.01)._worker()
    assert "conn" in seen                        # the worker really reached claim_next
    assert probe_can_write(dbpath)               # the worker's connection no longer holds the lock
