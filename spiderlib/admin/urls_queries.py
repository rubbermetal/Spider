"""Read-only queries for the URL browser: list, detail, links, counts."""

import sqlite3
from spiderlib.admin import urls_filter

LIST_COLUMNS = "id, url, host, seed_id, depth, status, http_status, title, fetched_at, hidden, approved, tags, error"

def list_urls(conn, f):
    where, params = urls_filter.where_clause(f)
    total_query = f"SELECT COUNT(*) FROM urls {where}"
    total = conn.execute(total_query, params).fetchone()[0]
    pg = urls_filter.pager(total, f["page"], f["per_page"])
    query = f"SELECT {LIST_COLUMNS} FROM urls {where} {urls_filter.order_clause(f)} LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [pg["per_page"], pg["offset"]]).fetchall()
    return ([dict(r) for r in rows], pg)

def get_url(conn, url_id):
    query = "SELECT urls.*, seeds.url AS seed_url FROM urls LEFT JOIN seeds ON seeds.id = urls.seed_id WHERE urls.id = ?"
    row = conn.execute(query, (url_id,)).fetchone()
    return dict(row) if row else None

def inbound_links(conn, url_id, limit=50):
    query = "SELECT u.id, u.url, u.title FROM links l JOIN urls u ON u.id = l.from_id WHERE l.to_url = (SELECT url FROM urls WHERE id = ?) ORDER BY u.id LIMIT ?"
    rows = conn.execute(query, (url_id, limit)).fetchall()
    return [dict(r) for r in rows]

def outbound_links(conn, url_id, limit=200):
    query = "SELECT l.to_url, u.id, u.status FROM links l LEFT JOIN urls u ON u.url = l.to_url WHERE l.from_id = ? ORDER BY l.rowid LIMIT ?"
    rows = conn.execute(query, (url_id, limit)).fetchall()
    return [{"to_url": r[0], "id": r[1], "status": r[2]} for r in rows]

def status_counts(conn):
    query = "SELECT status, COUNT(*) as count FROM urls GROUP BY status"
    rows = conn.execute(query).fetchall()
    return {r["status"]: r["count"] for r in rows}

def seed_options(conn):
    query = "SELECT id, url FROM seeds ORDER BY id"
    rows = conn.execute(query).fetchall()
    return [(r["id"], r["url"]) for r in rows]
