import itertools
import pytest
from spiderlib import db
from spiderlib.admin import urls_actions as ua

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

_counter = itertools.count(1)

def add(conn, url=None, status="done", tags="", hidden=0, approved=0, discovered_from=None, error=None, attempts=0):
    if url is None:
        url = "http://a.com/auto%d" % next(_counter)
    cursor = conn.execute(
        "INSERT INTO urls (url, host, added_at, status, tags, hidden, approved, discovered_from, error, attempts)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (url, "a.com", db.now(), status, tags, hidden, approved, discovered_from, error, attempts)
    )
    conn.commit()
    return cursor.lastrowid

def row(conn, id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM urls WHERE id = ?", (id,))
    return dict(cursor.fetchone())

def audit(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit ORDER BY id")
    return [dict(r) for r in cursor.fetchall()]

clean_tag = ua.clean_tag
apply_action = ua.apply_action
parse_ids = ua.parse_ids

def test_parse_ids():
    assert ua.parse_ids(["3", "x", "3", "-1", "0", "7", " 9 ", "2.5", ""]) == [3, 7, 9]
    assert ua.parse_ids([]) == []
    numeric_strings = [str(i) for i in range(1500)]
    assert len(ua.parse_ids(numeric_strings)) == 1000

def test_clean_tag():
    assert clean_tag(" News ") == "news"
    assert clean_tag("a-b_c9") == "a-b_c9"
    assert clean_tag("has space") is None
    assert clean_tag("x" * 31) is None
    assert clean_tag("") is None
    assert clean_tag("UPPER") == "upper"
    assert clean_tag("bad!") is None

def test_unknown_action_and_empty_ids(conn):
    assert apply_action(conn, "explode", [1]) == (0, "unknown action")
    assert apply_action(conn, "hide", []) == (0, "nothing selected")
    assert not audit(conn)

def test_requeue(conn):
    a = add(conn, status="error", error='x', attempts=3)
    b = add(conn, status="done")
    result = apply_action(conn, "requeue", [a, b])
    assert result == (2, None)
    assert row(conn, a)['attempts'] == 0
    assert row(conn, a)['error'] is None
    assert row(conn, a)['next_attempt_at'] is None
    assert row(conn, b)['attempts'] == 0
    assert row(conn, b)['error'] is None
    assert row(conn, b)['next_attempt_at'] is None
    audit_log = audit(conn)
    assert len(audit_log) == 1
    assert audit_log[0]['actor'] == "admin"
    assert audit_log[0]['action'] == "url_requeue"
    assert audit_log[0]['detail'] == "2 of 2 url(s)"

def test_hide_unhide_approve_unapprove(conn):
    a = add(conn)
    b = add(conn)
    result = apply_action(conn, "hide", [a])
    assert result == (1, None)
    assert row(conn, a)['hidden'] == 1
    assert row(conn, b)['hidden'] == 0
    result = apply_action(conn, "unhide", [a])
    assert result == (1, None)
    assert row(conn, a)['hidden'] == 0
    result = apply_action(conn, "approve", [a, b])
    assert result == (2, None)
    assert row(conn, a)['approved'] == 1
    assert row(conn, b)['approved'] == 1
    result = apply_action(conn, "unapprove", [b])
    assert result == (1, None)
    assert row(conn, a)['approved'] == 1
    assert row(conn, b)['approved'] == 0

def test_tag_add_and_remove(conn):
    a = add(conn)
    b = add(conn, tags="news")
    result = apply_action(conn, "tag_add", [a, b], " News ")
    assert result == (1, None)
    assert row(conn, a)['tags'] == "news"
    assert row(conn, b)['tags'] == "news"
    result = apply_action(conn, "tag_add", [a], "tech")
    assert result == (1, None)
    assert row(conn, a)['tags'] == "news,tech"
    result = apply_action(conn, "tag_remove", [a, b], "news")
    assert result == (2, None)
    assert row(conn, a)['tags'] == "tech"
    assert row(conn, b)['tags'] == ""
    result = apply_action(conn, "tag_remove", [a], "missing")
    assert result == (0, None)
    audit_log = audit(conn)
    assert audit_log[0]['detail'] == "1 of 2 url(s) tag=news"

def test_tag_invalid(conn):
    a = add(conn)
    assert apply_action(conn, "tag_add", [a], "bad tag") == (0, "invalid tag (letters, digits, - or _, up to 30)")
    assert apply_action(conn, "tag_remove", [a], "") == (0, "invalid tag (letters, digits, - or _, up to 30)")

def test_delete(conn):
    a = add(conn)
    b = add(conn, discovered_from=a)
    c = add(conn)
    conn.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (a, 'http://x.com/1'))
    conn.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (c, 'http://x.com/2'))
    conn.commit()
    result = apply_action(conn, "delete", [a])
    assert result == (1, None)
    assert row(conn, b)['discovered_from'] is None
    assert row(conn, c) is not None
    assert row(conn, c)['discovered_from'] is None
    links = conn.execute("SELECT * FROM links").fetchall()
    assert len(links) == 1
    assert links[0]['from_id'] == c
    result = apply_action(conn, "delete", [a])
    assert result == (0, None)
    audit_log = audit(conn)
    assert audit_log[0]['action'] == "url_delete"
