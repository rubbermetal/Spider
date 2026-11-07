import pytest
from spiderlib import db
from spiderlib.admin import domains_ops as ops

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def dom(conn, host):
    result = conn.execute("SELECT * FROM domains WHERE host = ?", (host,)).fetchone()
    return dict(result) if result else None

def audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id")]

def fake_fetcher(status, text):
    def fetcher(url, ua, timeout):
        fetcher.calls.append(url)
        return (status, text)
    fetcher.calls = []
    return fetcher

def test_clean_host():
    assert ops.clean_host(" Example.COM ") == "example.com"
    assert ops.clean_host("https://Sub.Example.com:8080/x") == "sub.example.com"
    assert ops.clean_host("a b") is None
    assert ops.clean_host("") is None
    assert ops.clean_host("-bad.com") is None
    assert ops.clean_host("x" * 300) is None
    assert ops.clean_host("a.com") == "a.com"
    assert ops.clean_host("under_score.com") is None

def test_block_and_unblock(conn):
    assert ops.set_blocked(conn, "Bad.com", True) is True
    assert dom(conn, "bad.com")["blocked"] == 1
    assert ops.set_blocked(conn, "bad.com", False) is True
    assert dom(conn, "bad.com")["blocked"] == 0
    assert ops.set_blocked(conn, "not a host", True) is False
    assert dom(conn, "not a host") is None
    audit_log = audit(conn)
    assert len(audit_log) == 2
    assert audit_log[0]["action"] == "domain_block"
    assert audit_log[0]["actor"] == "admin"
    assert audit_log[0]["detail"] == "bad.com"
    assert audit_log[1]["action"] == "domain_unblock"
    assert audit_log[1]["actor"] == "admin"
    assert audit_log[1]["detail"] == "bad.com"

def test_block_keeps_other_columns(conn):
    ops.set_notes(conn, "a.com", "keep me")
    ops.set_blocked(conn, "a.com", True)
    assert dom(conn, "a.com")["notes"] == "keep me"

def test_set_delay(conn):
    assert ops.set_delay(conn, "a.com", "2.5") is None
    assert dom(conn, "a.com")["delay_override"] == 2.5
    assert ops.set_delay(conn, "a.com", "") is None
    assert dom(conn, "a.com")["delay_override"] is None
    assert ops.set_delay(conn, "a.com", "abc") == "must be a number"
    assert ops.set_delay(conn, "a.com", "nan") == "must be a number"
    assert ops.set_delay(conn, "a.com", "-1") == "must be between 0 and 3600"
    assert ops.set_delay(conn, "a.com", "3601") == "must be between 0 and 3600"
    assert ops.set_delay(conn, "a.com", "0") is None
    assert dom(conn, "a.com")["delay_override"] == 0.0
    assert ops.set_delay(conn, "bad host", "1") == "invalid host"
    audit_log = audit(conn)
    assert len(audit_log) == 3  # "2.5", "" and "0" succeeded
    assert audit_log[0]["action"] == "domain_delay"
    assert audit_log[0]["actor"] == "admin"
    assert audit_log[0]["detail"] == "a.com: 2.5"

def test_set_notes(conn):
    assert ops.set_notes(conn, "a.com", "  hello  ") is None
    assert dom(conn, "a.com")["notes"] == "hello"
    assert ops.set_notes(conn, "a.com", "x" * 1001) == "notes are limited to 1000 characters"
    assert dom(conn, "a.com")["notes"] == "hello"
    assert ops.set_notes(conn, "a.com", "") is None
    assert dom(conn, "a.com")["notes"] == ""
    assert ops.set_notes(conn, "bad host", "note") == "invalid host"

def test_refetch_robots_uses_known_url_and_stores(conn):
    conn.execute("INSERT INTO urls (url, host, status, added_at) VALUES (?, ?, ?, ?)",
                ("http://a.com:8080/page", "a.com", "done", db.now()))
    f = fake_fetcher(200, "User-agent: *\nDisallow: /private/")
    status, err = ops.refetch_robots(conn, "a.com", dict(db.DEFAULT_SETTINGS), f)
    assert (status, err) == (200, None)
    assert f.calls == ["http://a.com:8080/robots.txt"]
    domain = dom(conn, "a.com")
    assert "Disallow: /private/" in domain["robots_txt"]
    assert domain["robots_status"] == 200
    audit_log = audit(conn)
    assert len(audit_log) == 1
    assert audit_log[0]["action"] == "domain_robots_refetch"
    assert audit_log[0]["actor"] == "admin"
    assert audit_log[0]["detail"] == "a.com: status 200"

def test_refetch_forces_a_new_fetch(conn):
    f = fake_fetcher(200, "User-agent: *\nDisallow: /private/")
    ops.refetch_robots(conn, "a.com", dict(db.DEFAULT_SETTINGS), f)
    ops.refetch_robots(conn, "a.com", dict(db.DEFAULT_SETTINGS), f)
    assert len(f.calls) == 2
    assert f.calls[0] == "https://a.com/robots.txt"
    assert f.calls[1] == "https://a.com/robots.txt"
    f = fake_fetcher(200, "User-agent: *\nDisallow: /private/")
    status, err = ops.refetch_robots(conn, "new.org", dict(db.DEFAULT_SETTINGS), f)
    assert f.calls[0] == "https://new.org/robots.txt"
    assert (status, err) == (200, None)
    assert ops.refetch_robots(conn, "bad host", dict(db.DEFAULT_SETTINGS), f) == (None, "invalid host")
    assert f.calls == ["https://new.org/robots.txt"]  # the invalid host never reached the fetcher
