import pytest
from spiderlib.admin import urls_filter as uf

def test_defaults():
    assert uf.parse_filters({}) == {
        "status": "", "host": "", "q": "", "tag": "", "seed": None, "hidden": "",
        "approved": "", "sort": "id", "order": "desc", "page": 1, "per_page": 50
    }

def test_valid_values():
    assert uf.parse_filters({
        "status": "done", "host": " a.com ", "q": "hello", "tag": " News ",
        "seed": "3", "hidden": "yes", "approved": "no", "sort": "fetched_at",
        "order": "asc", "page": "4", "per_page": "100"
    }) == {
        "status": "done", "host": "a.com", "q": "hello", "tag": "news", "seed": 3,
        "hidden": "yes", "approved": "no", "sort": "fetched_at", "order": "asc",
        "page": 4, "per_page": 100
    }

def test_invalid_values_fall_back():
    defaults = {
        "status": "", "host": "", "q": "", "tag": "", "seed": None, "hidden": "",
        "approved": "", "sort": "id", "order": "desc", "page": 1, "per_page": 50
    }
    assert uf.parse_filters({
        "status": "nope", "seed": "abc", "hidden": "maybe",
        "sort": "password; DROP TABLE urls", "order": "sideways", "page": "0",
        "per_page": "7"
    }) == defaults
    assert uf.parse_filters({"page": "x"})["page"] == 1
    assert uf.parse_filters({"seed": "-2"})["seed"] is None
    assert uf.parse_filters({"seed": "0"})["seed"] is None

def test_long_text_is_cut():
    long_text = "a" * 500
    assert len(uf.parse_filters({"q": long_text})["q"]) == 200
    assert len(uf.parse_filters({"host": long_text})["host"]) == 200
    assert len(uf.parse_filters({"tag": long_text})["tag"]) == 30

def test_where_clause_empty():
    assert uf.where_clause(uf.parse_filters({})) == ("", [])

def test_where_clause_all():
    f = uf.parse_filters({
        "status": "done", "host": "a.com", "q": "x", "seed": "2", "hidden": "no",
        "approved": "yes", "tag": "news"
    })
    sql, params = uf.where_clause(f)
    assert sql.startswith(" WHERE ")
    assert "status = ?" in sql
    assert "host LIKE ?" in sql
    assert "url LIKE ?" in sql
    assert "seed_id = ?" in sql
    assert "hidden = 0" in sql
    assert "approved = 1" in sql
    assert "tags" in sql
    assert params == ["done", "%a.com%", "%x%", "%x%", "%x%", 2, "%,news,%"]

def test_like_escapes():
    f = uf.parse_filters({"q": "50%_off"})
    sql, params = uf.where_clause(f)
    assert params[0] == "%50\\%\\_off%"

def test_order_clause():
    assert uf.order_clause(uf.parse_filters({})) == "ORDER BY id DESC, id DESC"
    assert uf.order_clause(uf.parse_filters({"sort": "url", "order": "asc"})) == "ORDER BY url ASC, id DESC"

def test_query_dict():
    assert uf.query_dict(uf.parse_filters({})) == {}
    assert uf.query_dict(uf.parse_filters({
        "status": "error", "sort": "url", "order": "asc", "per_page": "25", "page": "3", "seed": "5"
    })) == {"status": "error", "seed": 5, "sort": "url", "order": "asc", "per_page": 25}

def test_pager():
    assert uf.pager(0, 1, 50) == {
        "page": 1, "pages": 1, "total": 0, "per_page": 50, "offset": 0,
        "has_prev": False, "has_next": False, "first": 0, "last": 0
    }
    assert uf.pager(120, 2, 50) == {
        "page": 2, "pages": 3, "total": 120, "per_page": 50, "offset": 50,
        "has_prev": True, "has_next": True, "first": 51, "last": 100
    }
    assert uf.pager(120, 99, 50) == {
        "page": 3, "pages": 3, "total": 120, "per_page": 50, "offset": 100,
        "has_prev": True, "has_next": False, "first": 101, "last": 120
    }
    assert uf.pager(120, 0, 50) == {
        "page": 1, "pages": 3, "total": 120, "per_page": 50, "offset": 0,
        "has_prev": False, "has_next": True, "first": 1, "last": 50
    }
