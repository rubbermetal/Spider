import csv
import io
import json
import pytest
from spiderlib import db
from spiderlib.admin import export_ops as eo

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def add(conn, url, status="done", hidden=0, approved=0, **cols):
    conn.execute(
        "INSERT INTO urls (host, added_at, url, status, hidden, approved, title, description, tags, http_status, content_type, fetched_at) "
        "VALUES ('a.com', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.now(), url, status, hidden, approved, cols.get('title', ''), cols.get('description', ''), cols.get('tags', ''), cols.get('http_status', 200), cols.get('content_type', 'text/html'), cols.get('fetched_at', db.now()))
    )
    conn.commit()

def opts(**kw):
    return eo.parse_options(kw)[0]

count_rows = eo.count_rows
fetch_rows = eo.fetch_rows

def test_parse_options_defaults():
    assert eo.parse_options({}) == ({"format": "csv", "status": "", "hidden": "exclude", "approved": "any"}, None)

def test_parse_options_valid():
    assert eo.parse_options({"format": "json", "status": "done", "hidden": "include", "approved": "only"}) == ({"format": "json", "status": "done", "hidden": "include", "approved": "only"}, None)

def test_parse_options_errors():
    assert eo.parse_options({"format": "xml"}) == (None, "format must be csv or json")
    assert eo.parse_options({"status": "weird"}) == (None, "unknown status")
    assert eo.parse_options({"hidden": "x"}) == (None, "hidden must be exclude or include")
    assert eo.parse_options({"approved": "x"}) == (None, "approved must be any or only")

def test_counts_and_filters(conn):
    add(conn, "http://a.com/p1", status="done", approved=1)
    add(conn, "http://a.com/p2", status="done", hidden=1)
    add(conn, "http://a.com/p3", status="error")
    add(conn, "http://a.com/p4", status="done", approved=0)

    assert count_rows(conn, opts()) == 3  # hidden excluded
    assert count_rows(conn, opts(hidden="include")) == 4
    assert count_rows(conn, opts(status="done")) == 2
    assert count_rows(conn, opts(approved="only")) == 1
    assert count_rows(conn, opts(approved="only", hidden="include")) == 1
    assert count_rows(conn, opts(status="error")) == 1

def test_fetch_rows_order_and_shape(conn):
    add(conn, "http://a.com/1")
    add(conn, "http://a.com/2")
    rows = fetch_rows(conn, opts())
    assert len(rows) == 2
    assert rows[0][0] < rows[1][0]  # id order
    assert len(rows[0]) == 11  # 11 values each

def test_render_csv(conn):
    add(conn, "http://a.com/1", title='Hello, "world"', description="D", tags="news,tech", approved=1, http_status=200, content_type="text/html", fetched_at="2026-11-06T10:00:00Z")
    body, mimetype, filename = eo.render(conn, opts())
    assert mimetype == "text/csv; charset=utf-8"
    assert filename.startswith("spider-urls-") and filename.endswith(".csv")
    rows = list(csv.DictReader(io.StringIO(body)))
    assert len(rows) == 1
    assert {k: rows[0][k] for k in ("url", "title", "tags", "approved", "http_status")} == {
        "url": "http://a.com/1",
        "title": 'Hello, "world"',
        "tags": "news,tech",
        "approved": "1",
        "http_status": "200"
    }
    assert list(rows[0].keys()) == eo.COLUMNS

def test_render_json(conn):
    add(conn, "http://a.com/1", title='Hello, "world"', description="D", tags="news,tech", approved=1, http_status=200, content_type="text/html", fetched_at="2026-11-06T10:00:00Z")
    body, mimetype, filename = eo.render(conn, opts(format="json"))
    assert mimetype == "application/json; charset=utf-8"
    assert filename.endswith(".json")
    data = json.loads(body)
    assert len(data) == 1
    assert {k: data[0][k] for k in ("url", "title", "tags", "approved", "http_status")} == {
        "url": "http://a.com/1",
        "title": 'Hello, "world"',
        "tags": "news,tech",
        "approved": True,
        "http_status": 200
    }
    assert list(data[0].keys()) == eo.COLUMNS

def test_render_empty(conn):
    body, mimetype, filename = eo.render(conn, opts())
    assert body.splitlines() == [",".join(eo.COLUMNS)]
    body, mimetype, filename = eo.render(conn, opts(format="json"))
    assert json.loads(body) == []

def test_unicode_survives(conn):
    add(conn, "http://a.com/1", title="Café ☕")
    body, mimetype, filename = eo.render(conn, opts())
    assert "Café ☕" in body
    body, mimetype, filename = eo.render(conn, opts(format="json"))
    data = json.loads(body)
    assert data[0]["title"] == "Café ☕"
