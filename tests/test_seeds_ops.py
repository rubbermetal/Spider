import pytest
from spiderlib import db, queue
from spiderlib.admin import seeds_ops as ops

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id")]

def set_status(conn, url, status):
    conn.execute("UPDATE urls SET status = ? WHERE url = ?", (status, url))
    conn.commit()

def test_add_from_form_ok(conn):
    seed_id, errors = ops.add_from_form(conn, {"url": "HTTP://Example.com", "max_depth": "2", "allow_external": "no"})
    assert errors == {}
    seed = ops.get_seed(conn, seed_id)
    assert seed["url"] == "http://example.com/"
    assert seed["max_depth"] == 2
    assert seed["allow_external"] == 0
    assert seed["max_pages"] is None
    urls = list(conn.execute("SELECT * FROM urls WHERE seed_id = ?", (seed_id,)))
    assert len(urls) == 1
    assert urls[0]["priority"] == 100
    audit_rows = audit(conn)
    assert len(audit_rows) == 1
    assert {k: audit_rows[0][k] for k in ("actor", "action", "detail")} == {"actor": "admin", "action": "seed_add", "detail": "http://example.com/"}

def test_add_from_form_errors(conn):
    assert ops.add_from_form(conn, {"url": ""}) == (None, {"url": "required"})
    assert "url" in ops.add_from_form(conn, {"url": "mailto:a@b.c"})[1]
    assert "max_depth" in ops.add_from_form(conn, {"url": "http://a.com", "max_depth": "99"})[1]
    seeds = list(conn.execute("SELECT * FROM seeds"))
    assert len(seeds) == 0
    audit_rows = audit(conn)
    assert len(audit_rows) == 0

def test_add_duplicate(conn):
    sid1, _ = ops.add_from_form(conn, {"url": "http://a.com"})
    sid2, errors = ops.add_from_form(conn, {"url": "http://a.com"})
    assert errors == {"url": "seed already exists"}
    seeds = list(conn.execute("SELECT * FROM seeds"))
    assert len(seeds) == 1

def test_list_seeds_counts(conn):
    sid_a, _ = ops.add_from_form(conn, {"url": "http://a.com"})
    sid_b, _ = ops.add_from_form(conn, {"url": "http://b.com"})
    queue.enqueue(conn, "http://a.com/1", seed_id=sid_a)
    queue.enqueue(conn, "http://a.com/2", seed_id=sid_a)
    set_status(conn, "http://a.com/", "done")
    set_status(conn, "http://a.com/1", "error")
    rows = ops.list_seeds(conn)
    assert len(rows) == 2
    assert rows[0]["id"] == sid_a
    assert rows[0]["total"] == 3
    assert rows[0]["queued"] == 1
    assert rows[0]["done"] == 1
    assert rows[0]["errors"] == 1
    assert rows[1]["id"] == sid_b
    assert rows[1]["total"] == 1
    assert rows[1]["queued"] == 1
    assert rows[1]["done"] == 0
    assert rows[1]["errors"] == 0

def test_update_from_form(conn):
    sid, _ = ops.add_from_form(conn, {"url": "http://a.com"})
    ok, errors = ops.update_from_form(conn, sid, {"max_depth": "4", "max_pages": "10", "recrawl_hours": "12", "allow_external": "yes"})
    assert ok
    assert errors == {}
    seed = ops.get_seed(conn, sid)
    assert seed["max_depth"] == 4
    assert seed["max_pages"] == 10
    assert seed["recrawl_hours"] == 12
    assert seed["allow_external"] == 1
    ok, errors = ops.update_from_form(conn, sid, {})
    assert ok
    assert errors == {}
    seed = ops.get_seed(conn, sid)
    assert seed["max_depth"] is None
    assert seed["max_pages"] is None
    assert seed["recrawl_hours"] is None
    assert seed["allow_external"] is None
    ok, errors = ops.update_from_form(conn, sid, {"max_depth": "invalid"})
    assert not ok
    assert "max_depth" in errors
    ok, errors = ops.update_from_form(conn, 999, {})
    assert not ok
    assert errors == {"seed": "not found"}
    audit_rows = audit(conn)
    assert any(row["action"] == "seed_edit" for row in audit_rows)

def test_set_enabled(conn):
    sid, _ = ops.add_from_form(conn, {"url": "http://a.com"})
    assert ops.set_enabled(conn, sid, False)
    seed = list(conn.execute("SELECT * FROM seeds WHERE id = ?", (sid,)))[0]
    assert seed["enabled"] == 0
    audit_rows = audit(conn)
    assert any(row["action"] == "seed_disable" for row in audit_rows)
    assert ops.set_enabled(conn, sid, True)
    seed = list(conn.execute("SELECT * FROM seeds WHERE id = ?", (sid,)))[0]
    assert seed["enabled"] == 1
    audit_rows = audit(conn)
    assert any(row["action"] == "seed_enable" for row in audit_rows)
    assert not ops.set_enabled(conn, 999, True)

def test_recrawl(conn):
    sid, _ = ops.add_from_form(conn, {"url": "http://a.com"})
    queue.enqueue(conn, "http://a.com/1", seed_id=sid)
    queue.enqueue(conn, "http://a.com/2", seed_id=sid)
    queue.enqueue(conn, "http://a.com/3", seed_id=sid)
    set_status(conn, "http://a.com/", "done")
    set_status(conn, "http://a.com/1", "error")
    set_status(conn, "http://a.com/2", "blocked")
    n = ops.recrawl(conn, sid)
    assert n == 3
    urls = list(conn.execute("SELECT * FROM urls WHERE seed_id = ?", (sid,)))
    for url in urls:
        assert url["status"] == "queued"
        assert url["attempts"] == 0
        assert url["error"] is None
    audit_rows = audit(conn)
    assert any(row["action"] == "seed_recrawl" and row["detail"] == "http://a.com/: requeued 3" for row in audit_rows)
    assert ops.recrawl(conn, 999) is None

def test_delete_seed(conn):
    sid, _ = ops.add_from_form(conn, {"url": "http://a.com"})
    queue.enqueue(conn, "http://a.com/1", seed_id=sid)
    queue.enqueue(conn, "http://a.com/2", seed_id=sid)
    set_status(conn, "http://a.com/2", "done")
    result = ops.delete_seed(conn, sid)
    assert result == {"queued_removed": 2, "pages_kept": 1}
    seeds = list(conn.execute("SELECT * FROM seeds"))
    assert len(seeds) == 0
    urls = list(conn.execute("SELECT * FROM urls"))
    assert [u["url"] for u in urls] == ["http://a.com/2"]
    assert urls[0]["seed_id"] is None
    audit_rows = audit(conn)
    assert any(row["action"] == "seed_delete" for row in audit_rows)
    assert ops.delete_seed(conn, 999) is None
