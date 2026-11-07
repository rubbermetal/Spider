import pytest
from spiderlib import db
from spiderlib.admin import domains_queries as dq

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def add(conn, url, host, status="done", **cols):
    data = {"url": url, "host": host, "status": status, "added_at": db.now(), **cols}
    conn.execute(
        "INSERT INTO urls (%s) VALUES (%s)" % (", ".join(data), ", ".join("?" * len(data))),
        list(data.values()))
    conn.commit()

def dom(conn, host, **cols):
    data = {"host": host, **cols}
    conn.execute(
        "INSERT INTO domains (%s) VALUES (%s)" % (", ".join(data), ", ".join("?" * len(data))),
        list(data.values()))
    conn.commit()

def test_parse_args_defaults_and_invalid():
    assert dq.parse_args({}) == {"q": "", "blocked": "", "sort": "total", "order": "desc", "page": 1, "per_page": 50}
    assert dq.parse_args({"blocked": "maybe", "sort": "evil", "order": "up", "page": "0", "per_page": "7"}) == {"q": "", "blocked": "", "sort": "total", "order": "desc", "page": 1, "per_page": 50}
    assert dq.parse_args({"q": " a.com ", "blocked": "yes", "sort": "host", "order": "asc", "page": "3", "per_page": "25"}) == {"q": "a.com", "blocked": "yes", "sort": "host", "order": "asc", "page": 3, "per_page": 25}

def test_query_dict():
    assert dq.query_dict(dq.parse_args({})) == {}
    assert dq.query_dict(dq.parse_args({"q": "x", "blocked": "no", "sort": "host", "order": "asc", "per_page": "100", "page": "4"})) == {"q": "x", "blocked": "no", "sort": "host", "order": "asc", "per_page": 100}

def test_list_counts_per_host(conn):
    add(conn, "http://a.com/page1", "a.com", "done")
    add(conn, "http://a.com/page2", "a.com", "done")
    add(conn, "http://a.com/page3", "a.com", "error")
    add(conn, "http://a.com/page4", "a.com", "queued")
    add(conn, "http://b.com/page1", "b.com", "fetching")
    
    rows, pg = dq.list_domains(conn, dq.parse_args({}))
    assert pg["total"] == 2
    assert rows[0]["host"] == "a.com"
    assert rows[0]["total"] == 4
    assert rows[0]["done"] == 2
    assert rows[0]["errors"] == 1
    assert rows[0]["queued"] == 1
    assert rows[0]["blocked"] == 0
    assert rows[0]["delay_override"] is None
    assert rows[0]["notes"] == ""
    assert rows[1]["host"] == "b.com"
    assert rows[1]["total"] == 1
    assert rows[1]["queued"] == 1

def test_hosts_from_domains_table_only(conn):
    dom(conn, "blocked-only.com", blocked=1, notes="spam")
    rows, pg = dq.list_domains(conn, dq.parse_args({}))
    assert pg["total"] == 1
    assert rows[0]["host"] == "blocked-only.com"
    assert rows[0]["total"] == 0
    assert rows[0]["blocked"] == 1
    assert rows[0]["notes"] == "spam"

    add(conn, "http://blocked-only.com/page1", "blocked-only.com", "done")
    rows, pg = dq.list_domains(conn, dq.parse_args({}))
    assert pg["total"] == 1
    assert len(rows) == 1

def test_filters(conn):
    add(conn, "http://a.com/page1", "a.com")
    add(conn, "http://b.org/page1", "b.org")
    add(conn, "http://c.net/page1", "c.net")
    dom(conn, "b.org", blocked=1)

    args = dq.parse_args({"q": "a."})
    rows, pg = dq.list_domains(conn, args)
    assert pg["total"] == 1
    assert rows[0]["host"] == "a.com"

    args = dq.parse_args({"blocked": "yes"})
    rows, pg = dq.list_domains(conn, args)
    assert pg["total"] == 1
    assert rows[0]["host"] == "b.org"

    args = dq.parse_args({"blocked": "no"})
    rows, pg = dq.list_domains(conn, args)
    assert pg["total"] == 2
    assert rows[0]["host"] == "a.com"
    assert rows[1]["host"] == "c.net"

    args = dq.parse_args({"q": "%"})
    rows, pg = dq.list_domains(conn, args)
    assert pg["total"] == 0

def test_sort_and_paging(conn):
    for i in range(30):
        add(conn, f"http://h{i:02d}.com/page1", f"h{i:02d}.com")

    args = dq.parse_args({"sort": "host", "order": "asc", "per_page": "25"})
    rows, pg = dq.list_domains(conn, args)
    assert len(rows) == 25
    assert rows[0]["host"] == "h00.com"
    assert pg["pages"] == 2
    assert pg["has_next"]

    args = dq.parse_args({"sort": "host", "order": "asc", "per_page": "25", "page": "2"})
    rows, pg = dq.list_domains(conn, args)
    assert len(rows) == 5
    assert rows[0]["host"] == "h25.com"

    args = dq.parse_args({"sort": "host", "order": "asc", "per_page": "25", "page": "99"})
    rows, pg = dq.list_domains(conn, args)
    assert len(rows) == 5

def test_get_domain(conn):
    add(conn, "http://a.com/page1", "a.com", "done")
    add(conn, "http://a.com/page2", "a.com", "done")
    add(conn, "http://a.com/page3", "a.com", "error")
    dom(conn, "a.com", notes="n", robots_txt="Disallow: /x", robots_status=200, delay_override=1.5)

    d = dq.get_domain(conn, "a.com")
    assert d["total"] == 3
    assert d["done"] == 2
    assert d["errors"] == 1
    assert d["notes"] == "n"
    assert d["robots_txt"] == "Disallow: /x"
    assert d["robots_status"] == 200
    assert d["delay_override"] == 1.5
    assert d["blocked"] == 0

    assert dq.get_domain(conn, "unknown.com") is None

    dom(conn, "unknown.com", blocked=1)
    d = dq.get_domain(conn, "unknown.com")
    assert d["total"] == 0
    assert d["blocked"] == 1

def test_recent_urls(conn):
    add(conn, "http://a.com/page1", "a.com", "done", title="Title 1")
    add(conn, "http://a.com/page2", "a.com", "done", title="Title 2")
    add(conn, "http://a.com/page3", "a.com", "done", title="Title 3")
    add(conn, "http://a.com/page4", "a.com", "done", title="Title 4")
    add(conn, "http://a.com/page5", "a.com", "done", title="Title 5")

    urls = dq.recent_urls(conn, "a.com", limit=3)
    assert len(urls) == 3
    assert urls[0]["title"] == "Title 5"
    assert urls[1]["title"] == "Title 4"
    assert urls[2]["title"] == "Title 3"

    urls = dq.recent_urls(conn, "b.com", limit=3)
    assert len(urls) == 0

    urls = dq.recent_urls(conn, "unknown.com", limit=3)
    assert len(urls) == 0
