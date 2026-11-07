import pytest
from spiderlib import db
from spiderlib.admin import errors_ops as eo

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def add(conn, url, status="error", http_status=None, error=None, attempts=3):
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO urls (url, status, http_status, error, attempts, added_at, host) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url, status, http_status, error, attempts, db.now(), "a.com")
    )
    lastrowid = cursor.lastrowid
    conn.commit()
    return lastrowid

def row(conn, id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM urls WHERE id = ?", (id,))
    return dict(cursor.fetchone())

def audit(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit ORDER BY id")
    return [dict(r) for r in cursor.fetchall()]

def test_retry_group_requeues_only_that_group(conn):
    a = add(conn, "http://a.com/1", error="timed out")
    b = add(conn, "http://a.com/2", error="timed out")
    c = add(conn, "http://a.com/3", http_status=404, error="HTTP 404")
    n = eo.retry_group(conn, "timeout")
    assert n == 2
    assert row(conn, a)["status"] == "queued"
    assert row(conn, a)["attempts"] == 0
    assert row(conn, a)["error"] is None
    assert row(conn, a)["next_attempt_at"] is None
    assert row(conn, b)["status"] == "queued"
    assert row(conn, b)["attempts"] == 0
    assert row(conn, b)["error"] is None
    assert row(conn, b)["next_attempt_at"] is None
    assert row(conn, c)["status"] == "error"
    assert row(conn, c)["attempts"] == 3

def test_retry_group_blocked(conn):
    add(conn, "http://a.com/1", status="blocked", error="robots.txt")
    n = eo.retry_group(conn, "blocked-robots")
    assert n == 1
    assert row(conn, 1)["status"] == "queued"
    assert row(conn, 1)["error"] is None

def test_retry_group_invalid_kind(conn):
    assert eo.retry_group(conn, "../etc") is None
    assert eo.retry_group(conn, "nope") is None
    assert audit(conn) == []

def test_retry_group_empty_group_returns_zero(conn):
    n = eo.retry_group(conn, "dns")
    assert n == 0
    audit_entries = audit(conn)
    assert len(audit_entries) == 1
    assert audit_entries[0]["actor"] == "admin"
    assert audit_entries[0]["action"] == "errors_retry_group"
    assert audit_entries[0]["detail"] == "dns: requeued 0"

def test_audit_entry(conn):
    a = add(conn, "http://a.com/1", error="timed out")
    b = add(conn, "http://a.com/2", error="timed out")
    n = eo.retry_group(conn, "timeout")
    assert n == 2
    audit_entries = audit(conn)
    assert len(audit_entries) == 1
    assert audit_entries[0]["actor"] == "admin"
    assert audit_entries[0]["action"] == "errors_retry_group"
    assert audit_entries[0]["detail"] == "timeout: requeued 2"

def test_many_rows_are_chunked(conn):
    urls = [("http://a.com/{}".format(i), "error", "timed out") for i in range(1200)]
    cursor = conn.cursor()
    cursor.executemany(
        "INSERT INTO urls (url, status, error, added_at, host) VALUES (?, ?, ?, ?, ?)",
        [(url, status, error, db.now(), "a.com") for url, status, error in urls]
    )
    conn.commit()
    n = eo.retry_group(conn, "timeout")
    assert n == 1200
    cursor.execute("SELECT COUNT(*) FROM urls WHERE status = 'queued'")
    assert cursor.fetchone()[0] == 1200
