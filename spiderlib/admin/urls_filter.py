"""URL browser filters.

This module provides functions to parse URL query strings into filter dictionaries
and build SQL clauses for filtering and sorting.

Usage Example:
    args = {
        "status": "queued",
        "host": "example.com",
        "q": "search term",
        "tag": "example",
        "seed": "123",
        "hidden": "yes",
        "approved": "no",
        "sort": "fetched_at",
        "order": "asc",
        "page": "2",
        "per_page": "50"
    }
    filters = parse_filters(args)
    sql, params = where_clause(filters)
    order = order_clause(filters)
    query = query_dict(filters)
    pagination = pager(100, 2, 50)
"""

import re
from math import ceil

# Constants
STATUSES = ("queued", "fetching", "done", "error", "blocked", "skipped")
SORTS = ("id", "fetched_at", "url", "status", "depth", "http_status", "host")
PER_PAGE_CHOICES = (25, 50, 100)

def parse_filters(args):
    """Parse the query string into a filter dictionary."""
    def _parse_value(name, default, valid_values=None, transform=None):
        value = args.get(name, "").strip()
        if transform:
            value = transform(value)
        if valid_values and value not in valid_values:
            value = default
        return value

    return {
        "status": _parse_value("status", "", STATUSES),
        "host": _parse_value("host", "", transform=lambda x: x[:200]),
        "q": _parse_value("q", "", transform=lambda x: x[:200]),
        "tag": _parse_value("tag", "", transform=lambda x: x[:30].lower()),
        "seed": _parse_value("seed", None, transform=lambda x: int(x) if x.isdigit() and int(x) > 0 else None),
        "hidden": _parse_value("hidden", "", ("yes", "no")),
        "approved": _parse_value("approved", "", ("yes", "no")),
        "sort": _parse_value("sort", "id", SORTS),
        "order": _parse_value("order", "desc", ("asc", "desc")),
        "page": _parse_value("page", 1, transform=lambda x: int(x) if x.isdigit() and int(x) >= 1 else 1),
        "per_page": _parse_value("per_page", 50, transform=_per_page)
    }

def _escape(text):
    """Escape backslash, % and _ for use in a LIKE pattern with ESCAPE '\\'."""
    return re.sub(r"([%_\\])", r"\\\1", text)

def _like(text):
    """Contains-pattern for LIKE."""
    return f"%{_escape(text)}%"

def _per_page(text):
    return int(text) if text.isdigit() and int(text) in PER_PAGE_CHOICES else 50

def where_clause(f):
    """Build the WHERE clause for SQL query."""
    conditions = []
    params = []

    if f["status"]:
        conditions.append("status = ?")
        params.append(f["status"])

    if f["host"]:
        conditions.append("host LIKE ? ESCAPE '\\'")
        params.append(_like(f["host"]))

    if f["q"]:
        conditions.append("(url LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
        params.extend([_like(f["q"])] * 3)

    if f["seed"] is not None:
        conditions.append("seed_id = ?")
        params.append(f["seed"])

    if f["hidden"]:
        conditions.append("hidden = 1" if f["hidden"] == "yes" else "hidden = 0")

    if f["approved"]:
        conditions.append("approved = 1" if f["approved"] == "yes" else "approved = 0")

    if f["tag"]:
        conditions.append("(',' || tags || ',') LIKE ? ESCAPE '\\'")
        params.append(f"%,{_escape(f['tag'])},%")

    sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    return sql, params

def order_clause(f):
    """Build the ORDER BY clause for SQL query."""
    return f"ORDER BY {f['sort']} {'ASC' if f['order'] == 'asc' else 'DESC'}, id DESC"

def query_dict(f):
    """Build a dictionary for query parameters."""
    query = {}
    if f["status"]:
        query["status"] = f["status"]
    if f["host"]:
        query["host"] = f["host"]
    if f["q"]:
        query["q"] = f["q"]
    if f["tag"]:
        query["tag"] = f["tag"]
    if f["seed"] is not None:
        query["seed"] = f["seed"]
    if f["hidden"]:
        query["hidden"] = f["hidden"]
    if f["approved"]:
        query["approved"] = f["approved"]
    if f["sort"] != "id":
        query["sort"] = f["sort"]
    if f["order"] != "desc":
        query["order"] = f["order"]
    if f["per_page"] != 50:
        query["per_page"] = f["per_page"]
    return query

def pager(total, page, per_page):
    """Calculate pagination information."""
    pages = max(1, ceil(total / per_page))
    page = max(1, min(page, pages))
    offset = (page - 1) * per_page
    return {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page,
        "offset": offset,
        "has_prev": page > 1,
        "has_next": page < pages,
        "first": offset + 1 if total else 0,
        "last": min(offset + per_page, total)
    }
