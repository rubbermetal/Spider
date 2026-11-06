"""
Usage example:
from spiderlib import db, queue

conn = db.connect("spider.db")
queue.add_seed(conn, "https://example.com", max_depth=2, max_pages=100)
url_id = queue.enqueue(conn, "https://example.com/page1")
claimed_url = queue.claim_next(conn)
queue.record_result(conn, claimed_url['id'], {"status": 200, "content_type": "text/html", "body": "<html>...</html>", "elapsed_ms": 100}, {"title": "Page 1", "description": "Description of page 1"}, "content_hash")
"""

from datetime import datetime, timedelta, timezone
import sqlite3
from spiderlib import db
from spiderlib.urls import normalize_url, host_of, registered_domain, is_same_site, has_skipped_extension

def _ts_after(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

def enqueue(conn, url, seed_id=None, depth=0, discovered_from=None, priority=0) -> int | None:
    normalized = normalize_url(url)
    if normalized is None:
        return None
    host = host_of(normalized)
    added_at = db.now()
    cur = conn.execute("""
        INSERT OR IGNORE INTO urls (url, host, seed_id, depth, priority, discovered_from, added_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (normalized, host, seed_id, depth, priority, discovered_from, added_at))
    conn.commit()
    return cur.lastrowid if cur.rowcount > 0 else None

def add_seed(conn, url, max_depth=None, max_pages=None, allow_external=None, recrawl_hours=None) -> int | None:
    normalized = normalize_url(url)
    if normalized is None:
        return None
    cursor = conn.execute("SELECT id FROM seeds WHERE url = ?", (normalized,))
    row = cursor.fetchone()
    if row:
        return row['id']
    added_at = db.now()
    conn.execute("""
        INSERT INTO seeds (url, max_depth, max_pages, allow_external, recrawl_hours, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (normalized, max_depth, max_pages, 1 if allow_external else 0 if allow_external is not None else None, recrawl_hours, added_at))
    conn.commit()
    seed_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    enqueue(conn, normalized, seed_id=seed_id, depth=0, priority=100)
    return seed_id

def in_scope(conn, url, depth, seed_id, settings) -> str | None:
    normalized = normalize_url(url)
    if normalized is None:
        return "bad-url"
    if has_skipped_extension(normalized):
        return "extension"
    seed = None
    if seed_id is not None:
        seed = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_id,)).fetchone()
    max_depth = seed["max_depth"] if seed is not None and seed["max_depth"] is not None else settings["max_depth"]
    if depth > max_depth:
        return "depth"
    host = host_of(normalized)
    if conn.execute("SELECT 1 FROM domains WHERE blocked = 1 AND (host = ? OR host = ?)", (host, registered_domain(host))).fetchone():
        return "blocked"
    if seed_id is not None:
        allow_external = bool(seed['allow_external']) if seed and seed['allow_external'] is not None else settings["allow_external"]
        if not allow_external and not is_same_site(normalized, seed['url']):
            return "external"
    if seed_id is not None and seed and seed['max_pages'] is not None:
        count = conn.execute("SELECT COUNT(*) FROM urls WHERE seed_id = ?", (seed_id,)).fetchone()[0]
        if count >= seed['max_pages']:
            return "seed-limit"
    count = conn.execute("SELECT COUNT(*) FROM urls WHERE host = ?", (host,)).fetchone()[0]
    if count >= settings["max_pages_per_domain"]:
        return "domain-limit"
    return None

def add_links(conn, from_id, links, seed_id, depth, settings) -> int:
    new_count = 0
    for link in links:
        conn.execute("INSERT OR IGNORE INTO links (from_id, to_url) VALUES (?, ?)", (from_id, link))
    conn.commit()
    for link in links:
        reason = in_scope(conn, link, depth + 1, seed_id, settings)
        if reason is None:
            if enqueue(conn, link, seed_id=seed_id, depth=depth + 1, discovered_from=from_id):
                new_count += 1
    conn.commit()
    return new_count

def claim_next(conn) -> sqlite3.Row | None:
    now_str = db.now()
    cursor = conn.execute("""
        UPDATE urls
        SET status = 'fetching', attempts = attempts + 1
        WHERE id = (
            SELECT id FROM urls
            WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
              AND (seed_id IS NULL OR seed_id NOT IN (SELECT id FROM seeds WHERE enabled = 0))
            ORDER BY priority DESC, id ASC
            LIMIT 1
        )
        RETURNING *
    """, (now_str,))
    row = cursor.fetchone()
    conn.commit()
    return row

def record_result(conn, url_id, result, parsed, digest) -> None:
    conn.execute("""
        UPDATE urls
        SET status = 'done', http_status = ?, content_type = ?, title = ?, description = ?, bytes = ?, content_hash = ?, fetch_ms = ?, fetched_at = ?, error = NULL, next_attempt_at = NULL, hidden = ?
        WHERE id = ?
    """, (
        result["status"], result["content_type"], parsed["title"] if parsed else None, parsed["description"] if parsed else None, len(result["body"]), digest, result["elapsed_ms"], db.now(), 1 if parsed and parsed.get("noindex") else 0, url_id
    ))
    conn.commit()

def record_failure(conn, url_id, result, settings) -> str:
    cursor = conn.execute("SELECT attempts FROM urls WHERE id = ?", (url_id,))
    attempts = cursor.fetchone()[0]
    retryable = result["error_kind"] in ("timeout", "connection") or (result["error_kind"] == "http" and result["status"] is not None and (result["status"] >= 500 or result["status"] == 429))
    if retryable and attempts <= settings["max_retries"]:
        new_status = "queued"
        next_attempt_at = _ts_after(settings["retry_backoff_seconds"] * attempts)
    else:
        new_status = "error"
        next_attempt_at = None
    conn.execute("""
        UPDATE urls
        SET status = ?, next_attempt_at = ?, http_status = ?, error = ?, fetch_ms = ?, fetched_at = ?
        WHERE id = ?
    """, (new_status, next_attempt_at, result["status"], result["error"] or result["error_kind"] or "error", result["elapsed_ms"], db.now(), url_id))
    conn.commit()
    return new_status

def set_status(conn, url_id, status, error=None) -> None:
    conn.execute("UPDATE urls SET status = ?, error = ?, fetched_at = ? WHERE id = ?", (status, error, db.now(), url_id))
    conn.commit()

def requeue(conn, url_id) -> None:
    conn.execute("UPDATE urls SET status = 'queued', attempts = 0, next_attempt_at = NULL, error = NULL WHERE id = ?", (url_id,))
    conn.commit()

def recover_stale(conn) -> int:
    cursor = conn.execute("UPDATE urls SET status = 'queued' WHERE status = 'fetching'")
    conn.commit()
    return cursor.rowcount
