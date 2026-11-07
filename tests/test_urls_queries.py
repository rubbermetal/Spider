import pytest
from spiderlib import db
from spiderlib.admin import urls_filter as uf, urls_queries as uq

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def add(conn, url, status="done", host=None, seed_id=None, title=None, description=None, depth=0, hidden=0, approved=0, tags="", fetched_at=None):
    if host is None:
        host = url.split("//")[1].split("/")[0]
    added_at = db.now()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO urls (url, host, seed_id, title, description, depth, status, http_status, fetched_at, hidden, approved, tags, added_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (url, host, seed_id, title, description, depth, status, None, fetched_at, hidden, approved, tags, added_at))
    conn.commit()
    return cursor.lastrowid

def filt(**kw):
    return uf.parse_filters({k: str(v) for k, v in kw.items()})

def test_list_all_and_default_order(conn):
    id1 = add(conn, "http://a.com/1")
    id2 = add(conn, "http://a.com/2")
    id3 = add(conn, "http://a.com/3")
    rows, pg = uq.list_urls(conn, filt())
    assert pg["total"] == 3
    assert [row["id"] for row in rows] == [id3, id2, id1]
    assert all(key in rows[0] for key in ["id", "url", "host", "seed_id", "depth", "status", "http_status", "title", "fetched_at", "hidden", "approved", "tags", "error"])

def test_filter_status_and_host(conn):
    add(conn, "http://a.com/1", status="done")
    add(conn, "http://a.com/2", status="error")
    add(conn, "http://b.com/1", status="done")
    rows, _ = uq.list_urls(conn, filt(status="done"))
    assert len(rows) == 2
    rows, _ = uq.list_urls(conn, filt(host="b.com"))
    assert len(rows) == 1
    rows, _ = uq.list_urls(conn, filt(status="done", host="a.com"))
    assert len(rows) == 1
    assert rows[0]["url"] == "http://a.com/1"

def test_search_text(conn):
    add(conn, "http://a.com/x", title="Cats and dogs")
    add(conn, "http://a.com/y", description="about Birds")
    add(conn, "http://a.com/z")
    rows, _ = uq.list_urls(conn, filt(q="cats"))
    assert len(rows) == 1
    rows, _ = uq.list_urls(conn, filt(q="birds"))
    assert len(rows) == 1
    rows, _ = uq.list_urls(conn, filt(q="a.com/"))
    assert len(rows) == 3
    rows, _ = uq.list_urls(conn, filt(q="%"))
    assert len(rows) == 0

def test_filter_flags_tags_seed(conn):
    add(conn, "http://a.com/1", hidden=1)
    add(conn, "http://a.com/2", approved=1)
    add(conn, "http://a.com/3", tags="news,tech")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO seeds (url, added_at) VALUES (?, ?)", ("http://s.com/", db.now()))
    conn.commit()
    seed_id = cursor.lastrowid
    add(conn, "http://a.com/4", seed_id=seed_id)
    rows, _ = uq.list_urls(conn, filt(hidden="yes"))
    assert len(rows) == 1
    rows, _ = uq.list_urls(conn, filt(hidden="no"))
    assert len(rows) == 3
    rows, _ = uq.list_urls(conn, filt(approved="yes"))
    assert len(rows) == 1
    rows, _ = uq.list_urls(conn, filt(tag="tech"))
    assert len(rows) == 1
    rows, _ = uq.list_urls(conn, filt(tag="new"))
    assert len(rows) == 0
    rows, _ = uq.list_urls(conn, filt(seed=seed_id))
    assert len(rows) == 1

def test_sort_and_paging(conn):
    for i in range(30):
        add(conn, f"http://a.com/{i}")
    rows, pg = uq.list_urls(conn, filt(per_page=25))
    assert len(rows) == 25
    assert pg["pages"] == 2
    assert pg["has_next"] is True
    rows, pg = uq.list_urls(conn, filt(page=2, per_page=25))
    assert len(rows) == 5
    rows, pg = uq.list_urls(conn, filt(page=99, per_page=25))
    assert len(rows) == 5
    rows, _ = uq.list_urls(conn, filt(sort="url", order="asc"))
    assert rows[0]["url"] == "http://a.com/0"

def test_get_url_includes_seed_url(conn):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO seeds (url, added_at) VALUES (?, ?)", ("http://s.com/", db.now()))
    conn.commit()
    seed_id = cursor.lastrowid
    url_id = add(conn, "http://a.com/x", seed_id=seed_id)
    u = uq.get_url(conn, url_id)
    assert u["seed_url"] == "http://s.com/"
    assert u["id"] == url_id
    assert "description" in u
    assert "content_hash" in u
    assert uq.get_url(conn, 999) is None
    url_id_no_seed = add(conn, "http://b.com/x")
    u_no_seed = uq.get_url(conn, url_id_no_seed)
    assert u_no_seed["seed_url"] is None

def test_links_inbound_outbound(conn):
    a_id = add(conn, "http://a.com/")
    b_id = add(conn, "http://a.com/b")
    c_id = add(conn, "http://a.com/c")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (a_id, "http://a.com/b"))
    cursor.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (a_id, "http://a.com/c"))
    cursor.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (a_id, "http://other.org/x"))
    cursor.execute("INSERT INTO links (from_id, to_url) VALUES (?, ?)", (b_id, "http://a.com/c"))
    conn.commit()
    inbound = uq.inbound_links(conn, c_id)
    assert [link["url"] for link in inbound] == ["http://a.com/", "http://a.com/b"]
    assert uq.inbound_links(conn, a_id) == []
    outbound = uq.outbound_links(conn, a_id)
    assert len(outbound) == 3
    assert outbound[0]["to_url"] == "http://a.com/b"
    assert outbound[0]["id"] == b_id
    assert outbound[0]["status"] == "done"
    assert outbound[2]["to_url"] == "http://other.org/x"
    assert outbound[2]["id"] is None
    assert outbound[2]["status"] is None

def test_status_counts_and_seed_options(conn):
    add(conn, "http://a.com/1", status="done")
    add(conn, "http://a.com/2", status="done")
    add(conn, "http://a.com/3", status="error")
    assert uq.status_counts(conn) == {"done": 2, "error": 1}
    assert uq.seed_options(conn) == []
    cursor = conn.cursor()
    cursor.execute("INSERT INTO seeds (url, added_at) VALUES (?, ?)", ("http://s.com/", db.now()))
    cursor.execute("INSERT INTO seeds (url, added_at) VALUES (?, ?)", ("http://t.com/", db.now()))
    conn.commit()
    assert uq.seed_options(conn) == [(1, "http://s.com/"), (2, "http://t.com/")]
