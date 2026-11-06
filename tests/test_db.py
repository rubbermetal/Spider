import re
import sqlite3
from spiderlib import db
import pytest

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def test_tables_exist(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert set(tables) >= {"settings", "seeds", "domains", "urls", "links", "log", "audit"}

def test_init_is_idempotent(conn):
    db.init_db(conn)
    db.init_db(conn)

def test_now_format():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", db.now()) is not None

def test_settings_defaults(conn):
    assert db.get_settings(conn) == db.DEFAULT_SETTINGS

def test_set_setting_roundtrip(conn):
    db.set_setting(conn, "respect_robots", False)
    db.set_setting(conn, "concurrency", 8)
    db.set_setting(conn, "default_delay", 0.5)
    db.set_setting(conn, "user_agent", "X/1")
    settings = db.get_settings(conn)
    assert {k: settings[k] for k in ("respect_robots", "concurrency", "default_delay", "user_agent")} == {
        "respect_robots": False,
        "concurrency": 8,
        "default_delay": 0.5,
        "user_agent": "X/1"
    }
    db.set_setting(conn, "respect_robots", True)
    settings = db.get_settings(conn)
    assert settings["respect_robots"] is True

def test_set_setting_unknown_key(conn):
    with pytest.raises(KeyError):
        db.set_setting(conn, "nope", 1)

def test_bad_stored_value_keeps_default(conn):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO settings VALUES ('concurrency','abc')")
    conn.commit()
    settings = db.get_settings(conn)
    assert settings["concurrency"] == db.DEFAULT_SETTINGS["concurrency"]
    cursor.execute("INSERT INTO settings VALUES ('unknown_key','1')")
    conn.commit()
    settings = db.get_settings(conn)
    assert "unknown_key" not in settings

def test_log_and_audit(conn):
    db.log_event(conn, "error", "boom")
    cursor = conn.cursor()
    cursor.execute("SELECT level, message FROM log")
    log_entries = cursor.fetchall()
    assert [tuple(r) for r in log_entries] == [("error", "boom")]
    db.audit(conn, "admin", "pause", "x")
    cursor.execute("SELECT actor, action, detail FROM audit")
    audit_entries = cursor.fetchall()
    assert [tuple(r) for r in audit_entries] == [("admin", "pause", "x")]

def test_stats_empty(conn):
    assert db.stats(conn) == {"by_status": {}, "total_urls": 0, "domains": 0, "errors_last_hour": 0}

def test_stats_counts(conn):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO urls (url, host, status, added_at) VALUES (?, ?, ?, ?)",
                   ("http://a.com/1", "a.com", "done", db.now()))
    cursor.execute("INSERT INTO urls (url, host, status, added_at) VALUES (?, ?, ?, ?)",
                   ("http://a.com/2", "a.com", "queued", db.now()))
    cursor.execute("INSERT INTO urls (url, host, status, added_at) VALUES (?, ?, ?, ?)",
                   ("http://b.com/1", "b.com", "done", db.now()))
    conn.commit()
    db.log_event(conn, "error", "x")
    db.log_event(conn, "info", "y")
    stats = db.stats(conn)
    assert stats == {
        "by_status": {"done": 2, "queued": 1},
        "total_urls": 3,
        "domains": 2,
        "errors_last_hour": 1
    }

def test_url_unique(conn):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO urls (url, host, status, added_at) VALUES (?, ?, ?, ?)",
                   ("http://a.com/1", "a.com", "done", db.now()))
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("INSERT INTO urls (url, host, status, added_at) VALUES (?, ?, ?, ?)",
                       ("http://a.com/1", "a.com", "done", db.now()))
        conn.commit()
