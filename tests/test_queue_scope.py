import pytest
from spiderlib import db, queue

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

def test_enqueue_normalizes_and_dedupes(conn):
    assert isinstance(queue.enqueue(conn, "HTTP://Example.com/a#x"), int)
    assert queue.enqueue(conn, "http://example.com/a") is None
    r = row(conn, "http://example.com/a")
    assert (r["url"], r["host"], r["status"]) == ("http://example.com/a", "example.com", "queued")
    assert queue.enqueue(conn, "mailto:a@b.c") is None

def test_add_seed(conn):
    sid = queue.add_seed(conn, "http://a.com", max_depth=2)
    assert conn.execute("SELECT max_depth FROM seeds WHERE id = ?", (sid,)).fetchone()[0] == 2
    r = row(conn, "http://a.com/")
    assert (r["url"], r["seed_id"], r["depth"], r["priority"]) == ("http://a.com/", sid, 0, 100)
    assert queue.add_seed(conn, "http://a.com", max_depth=2) == sid
    assert conn.execute("SELECT COUNT(*) FROM seeds").fetchone()[0] == 1
    assert queue.add_seed(conn, "ftp://x") is None

def test_in_scope_ok(conn):
    sid = queue.add_seed(conn, "http://a.com/")
    assert queue.in_scope(conn, "http://a.com/page", 1, sid, S) is None

def test_in_scope_reasons(conn):
    sid = queue.add_seed(conn, "http://a.com/", max_depth=2)
    assert queue.in_scope(conn, "http://a.com/pic.jpg", 1, sid, S) == "extension"
    assert queue.in_scope(conn, "http://a.com/x", 3, sid, S) == "depth"
    assert queue.in_scope(conn, "http://b.org/x", 1, sid, S) == "external"
    assert queue.in_scope(conn, "mailto:x@y.z", 1, sid, S) == "bad-url"

def test_in_scope_external_allowed(conn):
    sid = queue.add_seed(conn, "http://a.com/", allow_external=True)
    assert queue.in_scope(conn, "http://b.org/x", 1, sid, S) is None
    sid = queue.add_seed(conn, "http://a2.com/", allow_external=False)
    assert queue.in_scope(conn, "http://b.org/x", 1, sid, dict(S, allow_external=True)) == "external"

def test_in_scope_subdomain_same_site(conn):
    sid = queue.add_seed(conn, "http://a.com/")
    assert queue.in_scope(conn, "http://blog.a.com/x", 1, sid, S) is None

def test_in_scope_blocked(conn):
    conn.execute("INSERT INTO domains (host, blocked) VALUES ('bad.com', 1)")
    conn.commit()
    assert queue.in_scope(conn, "http://bad.com/x", 0, None, S) == "blocked"
    assert queue.in_scope(conn, "http://www.bad.com/x", 0, None, S) == "blocked"

def test_in_scope_no_seed_uses_settings(conn):
    assert queue.in_scope(conn, "http://a.com/x", 4, None, dict(S, max_depth=3)) == "depth"
    assert queue.in_scope(conn, "http://a.com/x", 3, None, dict(S, max_depth=3)) is None

def test_seed_limit(conn):
    sid = queue.add_seed(conn, "http://a.com/", max_pages=2)
    queue.enqueue(conn, "http://a.com/1", seed_id=sid)
    assert queue.in_scope(conn, "http://a.com/3", 0, sid, S) == "seed-limit"

def test_domain_limit(conn):
    settings = dict(S, max_pages_per_domain=2)
    queue.enqueue(conn, "http://c.com/1", seed_id=None)
    queue.enqueue(conn, "http://c.com/2", seed_id=None)
    assert queue.in_scope(conn, "http://c.com/3", 0, None, settings) == "domain-limit"

def test_add_links(conn):
    sid = queue.add_seed(conn, "http://a.com/")
    from_id = row(conn, "http://a.com/")["id"]
    links = ["http://a.com/p1", "http://a.com/p2", "http://b.org/x", "http://a.com/p1", "http://a.com/img.png"]
    n = queue.add_links(conn, from_id, links, sid, 0, S)
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0] == 3
    assert row(conn, "http://a.com/p1")["depth"] == 1
    assert row(conn, "http://a.com/p1")["discovered_from"] == from_id
    assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 4
