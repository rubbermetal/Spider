"""
Module for domain operations in the spiderlib admin.
"""

import re
import urllib.parse
import math
from spiderlib import db, robots

def clean_host(text):
    """Strip and lowercase the host. If it contains '://', use urllib.parse.urlsplit to extract the hostname.
    Return the host if it matches the regex ^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$, else return None."""
    text = text.strip().lower()
    if '://' in text:
        parsed = urllib.parse.urlsplit(text)
        text = parsed.hostname
        if not text:
            return None
    if re.match(r'^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$', text):
        return text
    return None

def set_blocked(conn, host, blocked):
    """Set the blocked status of a host. Return False if the host is invalid."""
    host = clean_host(host)
    if host is None:
        return False
    blocked_value = 1 if blocked else 0
    conn.execute("INSERT INTO domains (host, blocked) VALUES (?, ?) ON CONFLICT(host) DO UPDATE SET blocked = excluded.blocked", (host, blocked_value))
    conn.commit()
    action = "domain_block" if blocked else "domain_unblock"
    db.audit(conn, "admin", action, host)
    return True

def set_delay(conn, host, text):
    """Set the delay override for a host. Return an error message or None on success."""
    host = clean_host(host)
    if host is None:
        return "invalid host"
    text = (text or "").strip()
    if not text:
        value = None
    else:
        try:
            value = float(text)
        except ValueError:
            return "must be a number"
        if not math.isfinite(value):
            return "must be a number"
        if value < 0 or value > 3600:
            return "must be between 0 and 3600"
    conn.execute("INSERT INTO domains (host, delay_override) VALUES (?, ?) ON CONFLICT(host) DO UPDATE SET delay_override = excluded.delay_override", (host, value))
    conn.commit()
    db.audit(conn, "admin", "domain_delay", f"{host}: {value}")
    return None

def set_notes(conn, host, text):
    """Set the notes for a host. Return an error message or None on success."""
    host = clean_host(host)
    if host is None:
        return "invalid host"
    text = (text or "").strip()
    if len(text) > 1000:
        return "notes are limited to 1000 characters"
    conn.execute("INSERT INTO domains (host, notes) VALUES (?, ?) ON CONFLICT(host) DO UPDATE SET notes = excluded.notes", (host, text))
    conn.commit()
    db.audit(conn, "admin", "domain_notes", host)
    return None

def refetch_robots(conn, host, settings, fetcher=robots.fetch_robots_txt):
    """Refetch the robots.txt for a host. Return a tuple (status, error)."""
    host = clean_host(host)
    if host is None:
        return (None, "invalid host")
    row = conn.execute("SELECT url FROM urls WHERE host = ? ORDER BY id LIMIT 1", (host,)).fetchone()
    sample = row["url"] if row else f"https://{host}/"
    conn.execute("INSERT OR IGNORE INTO domains (host) VALUES (?)", (host,))
    conn.execute("UPDATE domains SET robots_fetched_at = NULL WHERE host = ?", (host,))
    conn.commit()
    robots.get_robots(conn, sample, settings, fetcher)
    row = conn.execute("SELECT robots_status FROM domains WHERE host = ?", (host,)).fetchone()
    status = row["robots_status"] if row else None
    db.audit(conn, "admin", "domain_robots_refetch", f"{host}: status {status}")
    return (status, None)
