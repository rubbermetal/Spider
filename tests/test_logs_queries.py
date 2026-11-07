import pytest
from spiderlib import db
from spiderlib.admin import logs_filter as lf, logs_queries as lq
from datetime import datetime, timezone

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def log(conn, level, message, ts=None):
    if ts is None:
        ts = db.now()
    conn.execute("INSERT INTO log (level, message, ts) VALUES (?, ?, ?)", (level, message, ts))
    conn.commit()

def aud(conn, actor, action, detail=""):
    db.audit(conn, actor, action, detail)

def test_list_log_newest_first_and_filters(conn):
    log(conn, "info", "started")
    log(conn, "error", "boom: timeout")
    log(conn, "warn", "slow host")
    log(conn, "error", "other failure")

    rows, pg = lq.list_log(conn, lf.parse_log_args({}))
    assert pg["total"] == 4
    assert [row["message"] for row in rows] == ["other failure", "slow host", "boom: timeout", "started"]
    assert all(row.keys() == {"id", "ts", "level", "message"} for row in rows)

    rows, pg = lq.list_log(conn, lf.parse_log_args({"level": "error"}))
    assert len(rows) == 2

    rows, pg = lq.list_log(conn, lf.parse_log_args({"q": "timeout"}))
    assert len(rows) == 1

    rows, pg = lq.list_log(conn, lf.parse_log_args({"q": "%"}))
    assert len(rows) == 0

    rows, pg = lq.list_log(conn, lf.parse_log_args({"q": "BOOM"}))
    assert len(rows) == 1

def test_list_log_paging(conn):
    for i in range(60):
        log(conn, "info", f"log {i}")

    rows, pg = lq.list_log(conn, lf.parse_log_args({"page": "1", "per_page": "25"}))
    assert len(rows) == 25
    assert pg["pages"] == 3

    rows, pg = lq.list_log(conn, lf.parse_log_args({"page": "3", "per_page": "25"}))
    assert len(rows) == 10

    rows, pg = lq.list_log(conn, lf.parse_log_args({"page": "99", "per_page": "25"}))
    assert len(rows) == 10

def test_list_audit_filters(conn):
    aud(conn, "admin", "seed_add", "http://a.com/")
    aud(conn, "cli", "stop", "")
    aud(conn, "admin", "url_hide", "2 of 2 url(s)")

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({}))
    assert len(rows) == 3
    assert all(row.keys() == {"id", "ts", "actor", "action", "detail"} for row in rows)

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({"actor": "admin"}))
    assert len(rows) == 2

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({"action": "stop"}))
    assert len(rows) == 1

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({"q": "a.com"}))
    assert len(rows) == 1

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({"q": "hide"}))
    assert len(rows) == 1

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({"actor": "admin", "action": "seed_add"}))
    assert len(rows) == 1

    rows, pg = lq.list_audit(conn, lf.parse_audit_args({"q": "%"}))
    assert len(rows) == 0

def test_audit_options(conn):
    aud(conn, "admin", "seed_add", "http://a.com/")
    aud(conn, "cli", "stop", "")
    aud(conn, "admin", "url_hide", "2 of 2 url(s)")

    assert lq.audit_options(conn) == {"actors": ["admin", "cli"], "actions": ["seed_add", "stop", "url_hide"]}

    conn.execute("DELETE FROM audit")
    conn.commit()
    assert lq.audit_options(conn) == {"actors": [], "actions": []}

def test_prune_log(conn):
    log(conn, "info", "old1", ts="2000-01-01T00:00:00Z")
    log(conn, "info", "old2", ts="2001-01-01T00:00:00Z")
    log(conn, "info", "new")

    n = lq.prune_log(conn, 30)
    assert n == 2

    rows = conn.execute("SELECT * FROM log").fetchall()
    assert len(rows) == 1
    assert rows[0]["message"] == "new"

    rows = conn.execute("SELECT * FROM audit").fetchall()
    assert len(rows) == 1
    assert rows[0]["actor"] == "admin"
    assert rows[0]["action"] == "logs_prune"
    assert rows[0]["detail"] == "older than 30 days: removed 2"

def test_prune_invalid_days(conn):
    assert lq.prune_log(conn, 0) is None
    assert lq.prune_log(conn, -5) is None
    assert lq.prune_log(conn, 99999) is None
    assert lq.prune_log(conn, "30") is None
    assert lq.prune_log(conn, True) is None
    assert lq.prune_log(conn, None) is None

    rows = conn.execute("SELECT * FROM log").fetchall()
    assert len(rows) == 0

    rows = conn.execute("SELECT * FROM audit").fetchall()
    assert len(rows) == 0

def test_audit_is_never_pruned(conn):
    aud(conn, "admin", "x")
    conn.execute("UPDATE audit SET ts = '2000-01-01T00:00:00Z'")
    conn.commit()

    lq.prune_log(conn, 1)

    rows = conn.execute("SELECT * FROM audit").fetchall()
    assert len(rows) == 2
