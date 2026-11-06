import pytest
from spiderlib import db, queue
from datetime import datetime, timedelta
import hashlib

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

S = dict(db.DEFAULT_SETTINGS)

def row(conn, url):
    return conn.execute("SELECT * FROM urls WHERE url = ?", (url,)).fetchone()

def fake_result(**kw):
    result = {
        "status": 200,
        "content_type": "text/html",
        "body": b"<html></html>",
        "elapsed_ms": 12,
        "error": None,
        "error_kind": None
    }
    result.update(kw)
    return result

def add_seed(conn, url, priority=100):
    queue.add_seed(conn, url)

def enqueue(conn, url, priority=0):
    queue.enqueue(conn, url, priority=priority)

def claim_next(conn):
    return queue.claim_next(conn)

def record_result(conn, id, result, parsed, content_hash):
    queue.record_result(conn, id, result, parsed, content_hash)

def record_failure(conn, id, result, settings):
    return queue.record_failure(conn, id, result, settings)

def set_status(conn, id, status, error=None):
    queue.set_status(conn, id, status, error)

def requeue(conn, id):
    queue.requeue(conn, id)

def recover_stale(conn):
    return queue.recover_stale(conn)

def test_claim_next_order_and_atomic(conn):
    add_seed(conn, "http://a.com/", priority=100)
    enqueue(conn, "http://a.com/x", priority=0)
    enqueue(conn, "http://a.com/y", priority=5)

    assert claim_next(conn) == row(conn, "http://a.com/")
    assert claim_next(conn) == row(conn, "http://a.com/y")
    assert claim_next(conn) == row(conn, "http://a.com/x")
    assert claim_next(conn) is None

    for url in ["http://a.com/", "http://a.com/y", "http://a.com/x"]:
        claimed_row = row(conn, url)
        assert claimed_row["status"] == "fetching"
        assert claimed_row["attempts"] == 1

def test_claim_respects_next_attempt_at(conn):
    enqueue(conn, "http://a.com/")
    conn.execute("UPDATE urls SET next_attempt_at='2999-01-01T00:00:00Z'")
    assert claim_next(conn) is None

    conn.execute("UPDATE urls SET next_attempt_at='2000-01-01T00:00:00Z'")
    assert claim_next(conn) is not None

def test_record_result(conn):
    enqueue(conn, "http://a.com/")
    claimed_row = claim_next(conn)
    parsed = {"title": "T", "description": "D", "noindex": False, "links": []}
    content_hash = hashlib.sha256(b"<html></html>").hexdigest()
    record_result(conn, claimed_row["id"], fake_result(), parsed, content_hash)

    row_data = row(conn, "http://a.com/")
    assert row_data["status"] == "done"
    assert row_data["http_status"] == 200
    assert row_data["title"] == "T"
    assert row_data["description"] == "D"
    assert row_data["bytes"] == len(b"<html></html>")
    assert row_data["content_hash"] == content_hash
    assert row_data["fetched_at"] is not None
    assert row_data["hidden"] == 0

    enqueue(conn, "http://b.com/")
    claimed_row = claim_next(conn)
    parsed = {"title": "T", "description": "D", "noindex": True, "links": []}
    record_result(conn, claimed_row["id"], fake_result(), parsed, content_hash)

    row_data = row(conn, "http://b.com/")
    assert row_data["hidden"] == 1

    enqueue(conn, "http://c.com/")
    claimed_row = claim_next(conn)
    parsed = None
    record_result(conn, claimed_row["id"], fake_result(), parsed, content_hash)

    row_data = row(conn, "http://c.com/")
    assert row_data["title"] is None
    assert row_data["status"] == "done"

def test_record_failure_retry_then_error(conn):
    S2 = dict(S, max_retries=2, retry_backoff_seconds=300)
    enqueue(conn, "http://a.com/")
    claimed_row = claim_next(conn)
    result = fake_result(status=None, error="timed out", error_kind="timeout")
    assert record_failure(conn, claimed_row["id"], result, S2) == "queued"
    row_data = row(conn, "http://a.com/")
    assert row_data["next_attempt_at"] is not None
    assert row_data["error"] == "timed out"

    conn.execute("UPDATE urls SET next_attempt_at=NULL")
    claimed_row = claim_next(conn)
    assert record_failure(conn, claimed_row["id"], result, S2) == "queued"

    conn.execute("UPDATE urls SET next_attempt_at=NULL")
    claimed_row = claim_next(conn)
    assert record_failure(conn, claimed_row["id"], result, S2) == "error"
    row_data = row(conn, "http://a.com/")
    assert row_data["next_attempt_at"] is None

def test_record_failure_not_retryable(conn):
    enqueue(conn, "http://a.com/")
    claimed_row = claim_next(conn)
    result = fake_result(status=404, error_kind="http")
    assert record_failure(conn, claimed_row["id"], result, S) == "error"

    enqueue(conn, "http://b.com/")
    claimed_row = claim_next(conn)
    result = fake_result(status=503, error_kind="http")
    assert record_failure(conn, claimed_row["id"], result, S) == "queued"

    enqueue(conn, "http://c.com/")
    claimed_row = claim_next(conn)
    result = fake_result(error_kind="dns")
    assert record_failure(conn, claimed_row["id"], result, S) == "error"

    enqueue(conn, "http://d.com/")
    claimed_row = claim_next(conn)
    result = fake_result(error_kind="ssl")
    assert record_failure(conn, claimed_row["id"], result, S) == "error"

def test_set_status_and_requeue(conn):
    enqueue(conn, "http://a.com/")
    claimed_row = claim_next(conn)
    set_status(conn, claimed_row["id"], "blocked", "robots.txt")
    row_data = row(conn, "http://a.com/")
    assert row_data["status"] == "blocked"
    assert row_data["error"] == "robots.txt"

    requeue(conn, claimed_row["id"])
    row_data = row(conn, "http://a.com/")
    assert row_data["status"] == "queued"
    assert row_data["attempts"] == 0
    assert row_data["error"] is None

def test_recover_stale(conn):
    enqueue(conn, "http://a.com/")
    enqueue(conn, "http://b.com/")
    claimed_row = claim_next(conn)
    set_status(conn, claimed_row["id"], "fetching")

    assert recover_stale(conn) == 1

    for url in ["http://a.com/", "http://b.com/"]:
        row_data = row(conn, url)
        assert row_data["status"] == "queued"


def test_disabled_seed_urls_not_claimed(conn):
    sid = queue.add_seed(conn, "http://a.com/")
    conn.execute("UPDATE seeds SET enabled = 0 WHERE id = ?", (sid,))
    conn.commit()
    assert queue.claim_next(conn) is None
    queue.enqueue(conn, "http://other.com/x")  # no seed: always claimable
    assert queue.claim_next(conn)["url"] == "http://other.com/x"
    conn.execute("UPDATE seeds SET enabled = 1 WHERE id = ?", (sid,))
    conn.commit()
    assert queue.claim_next(conn)["url"] == "http://a.com/"
