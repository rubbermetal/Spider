"""When must a seed be crawled again? Uses seeds.recrawl_hours and seeds.last_crawled.

Usage:
    schedule.next_due(seed_dict)      # "2026-11-07T10:00:00Z" or None
    schedule.requeue_due(conn)        # [(seed_id, urls_requeued), ...]
"""

import datetime
from spiderlib import db

def _parse(ts):
    """Parse a UTC timestamp string into a timezone-aware datetime object."""
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

def _fmt(dt):
    """Format a timezone-aware datetime object into a UTC timestamp string."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def next_due(seed):
    """
    Determine the next due time for a seed.

    :param seed: A dictionary representing the seed.
    :return: A UTC timestamp string if the seed needs to be crawled again, otherwise None.
    """
    recrawl_hours = seed.get("recrawl_hours")
    if not recrawl_hours or not seed.get("enabled", 1):
        return None

    reference = seed.get("last_crawled") or seed.get("added_at")
    if not reference:
        return None

    return _fmt(_parse(reference) + datetime.timedelta(hours=recrawl_hours))

def due_seeds(conn, now=None):
    """
    Get seeds that are due for crawling.

    :param conn: An open sqlite3 connection with row_factory set to sqlite3.Row.
    :param now: The current time as a UTC timestamp string. Defaults to db.now().
    :return: A list of dictionaries representing seeds that are due.
    """
    if now is None:
        now = db.now()

    seeds = conn.execute(
        "SELECT * FROM seeds WHERE enabled = 1 AND recrawl_hours IS NOT NULL ORDER BY id"
    ).fetchall()

    seeds = [dict(seed) for seed in seeds]
    return [seed for seed in seeds if next_due(seed) and next_due(seed) <= now]

def requeue_due(conn, now=None):
    """
    Requeue seeds that are due for crawling.

    :param conn: An open sqlite3 connection with row_factory set to sqlite3.Row.
    :param now: The current time as a UTC timestamp string. Defaults to db.now().
    :return: A list of tuples (seed_id, n) where n is the number of URLs requeued.
    """
    if now is None:
        now = db.now()

    result = []
    for seed in due_seeds(conn, now):
        # Check if a crawl of this seed is still in progress
        if conn.execute(
            "SELECT 1 FROM urls WHERE seed_id = ? AND status IN ('queued', 'fetching') LIMIT 1",
            (seed["id"],)
        ).fetchone():
            continue

        # Claim the seed with a compare-and-set
        cur = conn.execute(
            "UPDATE seeds SET last_crawled = ? WHERE id = ? AND COALESCE(last_crawled, '') = ?",
            (now, seed["id"], seed["last_crawled"] or "")
        )
        if cur.rowcount != 1:
            conn.commit()
            continue

        # Requeue the URLs
        n = conn.execute(
            "UPDATE urls SET status = 'queued', attempts = 0, next_attempt_at = NULL, error = NULL WHERE seed_id = ? AND status IN ('done', 'error', 'skipped', 'blocked')",
            (seed["id"],)
        ).rowcount
        conn.commit()
        db.audit(conn, "scheduler", "seed_recrawl", f"{seed['url']}: requeued {n}")
        result.append((seed["id"], n))

    return result
