import pytest
from spiderlib import db
from spiderlib.admin import errors_queries as eq

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def add(conn, url, host, status="error", http_status=None, error=None):
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO urls (url, host, status, http_status, error, added_at, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (url, host, status, http_status, error, db.now(), db.now()))
    lastrowid = cursor.lastrowid
    conn.commit()
    return lastrowid

def test_group_counts(conn):
    add(conn, "http://a.com/1", "a.com", error="timed out")
    add(conn, "http://b.com/1", "b.com", error="timed out")
    add(conn, "http://a.com/2", "a.com", error="HTTP 404", http_status=404)
    add(conn, "http://a.com/3", "a.com", status="blocked", error="robots.txt")
    add(conn, "http://c.com/1", "c.com", status="skipped", error="redirect out of scope")
    add(conn, "http://d.com/1", "d.com", status="done")

    groups = eq.group_counts(conn)
    assert len(groups) == 4
    assert groups[0] == {
        "kind": "timeout",
        "label": "Timeouts",
        "count": 2,
        "hosts": 2,
        "sample": "timed out"
    }
    assert groups[1] == {
        "kind": "blocked-robots",
        "label": "Blocked by robots.txt",
        "count": 1,
        "hosts": 1,
        "sample": "robots.txt"
    }
    assert groups[2] == {
        "kind": "http-404",
        "label": "HTTP 404",
        "count": 1,
        "hosts": 1,
        "sample": "HTTP 404"
    }
    assert groups[3] == {
        "kind": "skipped-redirect",
        "label": "Skipped (redirect)",
        "count": 1,
        "hosts": 1,
        "sample": "redirect out of scope"
    }

def test_group_counts_empty(conn):
    assert eq.group_counts(conn) == []

def test_sample_is_newest(conn):
    add(conn, "http://a.com/1", "a.com", error="timed out (first)")
    add(conn, "http://a.com/2", "a.com", error="timed out (second)")
    groups = eq.group_counts(conn)
    assert groups[0]["sample"] == "timed out (second)"

def test_list_group_and_paging(conn):
    for i in range(60):
        add(conn, f"http://a.com/{i}", "a.com", error="timed out")

    rows, pg = eq.list_group(conn, "timeout", page=1, per_page=50)
    assert len(rows) == 50
    assert pg["total"] == 60
    assert pg["pages"] == 2
    assert rows[0]["id"] > rows[-1]["id"]

    rows, pg = eq.list_group(conn, "timeout", page=2, per_page=50)
    assert len(rows) == 10

    rows, pg = eq.list_group(conn, "timeout", page=99, per_page=50)
    assert len(rows) == 10

    rows, pg = eq.list_group(conn, "dns", page=1, per_page=50)
    assert rows == []
    assert pg["total"] == 0

    for row in rows:
        assert set(row.keys()) == {"id", "url", "host", "status", "http_status", "error", "attempts", "fetched_at", "kind"}

def test_ids_in_group(conn):
    add(conn, "http://a.com/1", "a.com", error="timed out")
    add(conn, "http://a.com/2", "a.com", error="timed out")
    add(conn, "http://a.com/3", "a.com", error="timed out")
    add(conn, "http://a.com/4", "a.com", error="HTTP 404", http_status=404)

    ids = eq.ids_in_group(conn, "timeout")
    assert ids == [1, 2, 3]

    ids = eq.ids_in_group(conn, "http-404")
    assert ids == [4]

    ids = eq.ids_in_group(conn, "unknown")
    assert ids == []

def test_top_hosts(conn):
    add(conn, "http://a.com/1", "a.com", error="timed out")
    add(conn, "http://a.com/2", "a.com", error="HTTP 404", http_status=404)
    add(conn, "http://a.com/3", "a.com", error="robots.txt")
    add(conn, "http://b.com/1", "b.com", error="timed out")
    add(conn, "http://b.com/2", "b.com", error="timed out")
    add(conn, "http://c.com/1", "c.com", error="redirect out of scope")
    add(conn, "http://d.com/1", "d.com", status="done")

    hosts = eq.top_hosts(conn)
    assert hosts == [
        {"host": "a.com", "count": 3},
        {"host": "b.com", "count": 2},
        {"host": "c.com", "count": 1}
    ]

    hosts = eq.top_hosts(conn, limit=2)
    assert len(hosts) == 2

def test_total_problems(conn):
    add(conn, "http://a.com/1", "a.com", error="timed out")
    add(conn, "http://a.com/2", "a.com", error="HTTP 404", http_status=404)
    add(conn, "http://a.com/3", "a.com", error="robots.txt")
    add(conn, "http://a.com/4", "a.com", error="redirect out of scope")
    add(conn, "http://a.com/5", "a.com", status="done")
    add(conn, "http://a.com/6", "a.com", status="queued")

    assert eq.total_problems(conn) == 4


def test_total_problems_empty(conn):
    assert eq.total_problems(conn) == 0
