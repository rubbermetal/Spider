import pytest
from datetime import datetime, timedelta
from spiderlib import db, queue, schedule

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def seed(conn, url, hours=1, last=None, added="2026-11-01T00:00:00Z", enabled=1):
    conn.execute(
        "INSERT INTO seeds (url, enabled, recrawl_hours, last_crawled, added_at) VALUES (?, ?, ?, ?, ?)",
        (url, enabled, hours, last, added)
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def page(conn, url, seed_id, status="done"):
    conn.execute(
        "INSERT INTO urls (url, host, seed_id, status, added_at) VALUES (?, ?, ?, ?, ?)",
        (url, "a.com", seed_id, status, db.now())
    )
    conn.commit()

def audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id")]

def test_next_due():
    assert schedule.next_due({"recrawl_hours": 2, "enabled": 1, "last_crawled": "2026-11-06T10:00:00Z", "added_at": "2026-11-01T00:00:00Z"}) == "2026-11-06T12:00:00Z"
    assert schedule.next_due({"recrawl_hours": 24, "added_at": "2026-11-01T00:00:00Z"}) == "2026-11-02T00:00:00Z"
    assert schedule.next_due({"recrawl_hours": None, "enabled": 1, "last_crawled": "2026-11-06T10:00:00Z", "added_at": "2026-11-01T00:00:00Z"}) is None
    assert schedule.next_due({"recrawl_hours": 0, "enabled": 1, "last_crawled": "2026-11-06T10:00:00Z", "added_at": "2026-11-01T00:00:00Z"}) is None
    assert schedule.next_due({"recrawl_hours": 1, "enabled": 0, "last_crawled": "2026-11-06T10:00:00Z", "added_at": "2026-11-01T00:00:00Z"}) is None
    assert schedule.next_due({"recrawl_hours": 1}) is None

def test_due_seeds(conn):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-06T10:00:00Z")
    seed_b = seed(conn, "http://b.com", hours=24, last="2026-11-06T10:00:00Z")
    seed_c = seed(conn, "http://c.com", hours=None)
    seed_d = seed(conn, "http://d.com", hours=1, enabled=0, last="2026-10-01T00:00:00Z")

    due_seeds = schedule.due_seeds(conn, now="2026-11-06T11:30:00Z")
    assert len(due_seeds) == 1
    assert due_seeds[0]['id'] == seed_a
    assert due_seeds[0]['url'] == "http://a.com"

    due_seeds = schedule.due_seeds(conn, now="2026-11-07T11:00:00Z")
    assert len(due_seeds) == 2
    assert due_seeds[0]['id'] == seed_a
    assert due_seeds[0]['url'] == "http://a.com"
    assert due_seeds[1]['id'] == seed_b
    assert due_seeds[1]['url'] == "http://b.com"

    due_seeds = schedule.due_seeds(conn, now="2026-11-06T11:00:00Z")
    assert len(due_seeds) == 1
    assert due_seeds[0]['id'] == seed_a
    assert due_seeds[0]['url'] == "http://a.com"

def test_requeue_due_requeues_finished_pages(conn):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-04T10:00:00Z")
    page(conn, "http://a.com/page1", seed_a, status="done")
    page(conn, "http://a.com/page2", seed_a, status="error")
    page(conn, "http://a.com/page3", seed_a, status="skipped")
    page(conn, "http://a.com/page4", seed_a, status="blocked")

    result = schedule.requeue_due(conn, now="2026-11-06T12:00:00Z")
    assert result == [(seed_a, 4)]

    pages = conn.execute("SELECT * FROM urls WHERE seed_id = ?", (seed_a,)).fetchall()
    for p in pages:
        assert p['attempts'] == 0
        assert p['error'] is None

    seed_row = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_a,)).fetchone()
    assert seed_row['last_crawled'] == "2026-11-06T12:00:00Z"

    audit_rows = audit(conn)
    assert len(audit_rows) == 1
    assert audit_rows[0]['actor'] == "scheduler"
    assert audit_rows[0]['action'] == "seed_recrawl"
    assert audit_rows[0]['detail'] == "http://a.com: requeued 4"

def test_not_due_again_right_after(conn):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-04T10:00:00Z")
    page(conn, "http://a.com/page1", seed_a, status="done")
    page(conn, "http://a.com/page2", seed_a, status="error")
    page(conn, "http://a.com/page3", seed_a, status="skipped")
    page(conn, "http://a.com/page4", seed_a, status="blocked")

    schedule.requeue_due(conn, now="2026-11-06T12:00:00Z")
    result = schedule.requeue_due(conn, now="2026-11-06T12:00:00Z")
    assert result == []

    pages = conn.execute("SELECT * FROM urls WHERE seed_id = ?", (seed_a,)).fetchall()
    assert len(pages) == 4
    for p in pages:
        assert p['status'] == "queued"  # still the requeued state from the first call

def test_skips_seed_with_crawl_in_progress(conn):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-04T10:00:00Z")
    page(conn, "http://a.com/page1", seed_a, status="queued")
    page(conn, "http://a.com/page2", seed_a, status="done")

    result = schedule.requeue_due(conn, now="2026-11-06T12:00:00Z")
    assert result == []

    seed_row = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_a,)).fetchone()
    assert seed_row['last_crawled'] == "2026-11-04T10:00:00Z"

    page_row = conn.execute("SELECT * FROM urls WHERE seed_id = ? AND status = 'done'", (seed_a,)).fetchone()
    assert page_row['status'] == "done"

def test_other_seeds_unaffected(conn):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-04T10:00:00Z")
    seed_b = seed(conn, "http://b.com", hours=1, last="2026-11-04T10:00:00Z")
    page(conn, "http://a.com/page1", seed_a, status="done")
    page(conn, "http://b.com/page1", seed_b, status="done")
    page(conn, "http://c.com/loose", None, status="done")

    result = schedule.requeue_due(conn, now="2026-11-06T12:00:00Z")
    assert len(result) == 2
    assert result[0][0] == seed_a
    assert result[1][0] == seed_b

    page_row = conn.execute("SELECT * FROM urls WHERE seed_id IS NULL AND status = 'done'").fetchone()
    assert page_row['status'] == "done"

def test_compare_and_set_blocks_a_second_claimer(conn, monkeypatch):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-04T10:00:00Z")
    page(conn, "http://a.com/page1", seed_a, status="done")

    # A competing worker already claimed the seed after we read it: our copy is stale.
    stale = dict(conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_a,)).fetchone())
    conn.execute("UPDATE seeds SET last_crawled = ? WHERE id = ?", ("2026-11-06T11:59:00Z", seed_a))
    conn.commit()
    monkeypatch.setattr(schedule, "due_seeds", lambda conn, now=None: [stale])

    assert schedule.requeue_due(conn, now="2026-11-06T12:00:00Z") == []
    page_row = conn.execute("SELECT * FROM urls WHERE seed_id = ?", (seed_a,)).fetchone()
    assert page_row["status"] == "done"
    assert audit(conn) == []

def test_zero_pages_still_stamps(conn):
    seed_a = seed(conn, "http://a.com", hours=1, last="2026-11-04T10:00:00Z")

    result = schedule.requeue_due(conn, now="2026-11-06T12:00:00Z")
    assert result == [(seed_a, 0)]

    seed_row = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_a,)).fetchone()
    assert seed_row['last_crawled'] == "2026-11-06T12:00:00Z"
