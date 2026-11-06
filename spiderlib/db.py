"""
Usage example:
conn = connect("spider.db")
set_setting(conn, "respect_robots", False)
settings = get_settings(conn)
audit(conn, "admin", "set_setting", "respect_robots=0")
print(stats(conn))
"""

import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seeds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1,
  max_depth INTEGER,
  max_pages INTEGER,
  allow_external INTEGER,
  recrawl_hours INTEGER,
  last_crawled TEXT,
  added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS domains (
  host TEXT PRIMARY KEY,
  blocked INTEGER NOT NULL DEFAULT 0,
  delay_override REAL,
  robots_txt TEXT,
  robots_status INTEGER,
  robots_fetched_at TEXT,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS urls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL UNIQUE,
  host TEXT NOT NULL,
  seed_id INTEGER,
  depth INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  priority INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  discovered_from INTEGER,
  added_at TEXT NOT NULL,
  http_status INTEGER,
  content_type TEXT,
  title TEXT,
  description TEXT,
  bytes INTEGER,
  content_hash TEXT,
  fetch_ms INTEGER,
  fetched_at TEXT,
  error TEXT,
  hidden INTEGER NOT NULL DEFAULT 0,
  approved INTEGER NOT NULL DEFAULT 0,
  tags TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_urls_status ON urls (status, priority DESC, id);
CREATE INDEX IF NOT EXISTS idx_urls_host ON urls (host, status);
CREATE TABLE IF NOT EXISTS links (
  from_id INTEGER NOT NULL,
  to_url TEXT NOT NULL,
  PRIMARY KEY (from_id, to_url)
);
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
"""

DEFAULT_SETTINGS = {
    "user_agent": "SpiderBot/1.0 (+https://github.com/rubbermetal/Spider)",
    "respect_robots": True,
    "default_delay": 2.0,
    "concurrency": 4,
    "timeout": 15.0,
    "max_bytes": 2000000,
    "max_depth": 3,
    "max_pages_per_domain": 500,
    "allow_external": False,
    "max_retries": 2,
    "retry_backoff_seconds": 300,
    "crawl_state": "stopped"
}

def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    init_db(conn)
    return conn

def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()

def get_settings(conn) -> dict:
    settings = DEFAULT_SETTINGS.copy()
    cursor = conn.execute("SELECT key, value FROM settings")
    for row in cursor:
        key, value = row
        if key in settings:
            default_type = type(settings[key])
            try:
                if default_type is bool:
                    settings[key] = value.lower() in ("1", "true", "yes")
                elif default_type is int:
                    settings[key] = int(value)
                elif default_type is float:
                    settings[key] = float(value)
                else:
                    settings[key] = value
            except ValueError:
                settings[key] = DEFAULT_SETTINGS[key]
    return settings

def set_setting(conn, key: str, value):
    if key not in DEFAULT_SETTINGS:
        raise KeyError(f"Unknown setting key: {key}")
    value_str = "1" if isinstance(value, bool) and value else "0" if isinstance(value, bool) else str(value)
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?", (key, value_str, value_str))
    conn.commit()

def log_event(conn, level: str, message: str):
    conn.execute("INSERT INTO log (ts, level, message) VALUES (?, ?, ?)", (now(), level, message))
    conn.commit()

def audit(conn, actor: str, action: str, detail: str = ""):
    conn.execute("INSERT INTO audit (ts, actor, action, detail) VALUES (?, ?, ?, ?)", (now(), actor, action, detail))
    conn.commit()

def stats(conn) -> dict:
    cursor = conn.execute("SELECT status, COUNT(*) as count FROM urls GROUP BY status")
    by_status = {row['status']: row['count'] for row in cursor}
    cursor = conn.execute("SELECT COUNT(*) as total_urls FROM urls")
    total_urls = cursor.fetchone()['total_urls']
    cursor = conn.execute("SELECT COUNT(DISTINCT host) as domains FROM urls")
    domains = cursor.fetchone()['domains']
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor = conn.execute("SELECT COUNT(*) as errors_last_hour FROM log WHERE level = 'error' AND ts >= ?", (one_hour_ago,))
    errors_last_hour = cursor.fetchone()['errors_last_hour']
    return {
        "by_status": by_status,
        "total_urls": total_urls,
        "domains": domains,
        "errors_last_hour": errors_last_hour
    }

def get_seed_url(conn, seed_id) -> str | None:
    """Get the `url` of the seeds row with the given id, or None."""
    cursor = conn.execute("SELECT url FROM seeds WHERE id = ?", (seed_id,))
    row = cursor.fetchone()
    return row['url'] if row else None

def get_seeds(conn) -> list:
    """Get a list of seeds with their statistics."""
    query = """
    SELECT
        seeds.id,
        seeds.url,
        seeds.enabled,
        seeds.max_depth,
        seeds.max_pages,
        seeds.allow_external,
        (SELECT COUNT(*) FROM urls WHERE urls.seed_id = seeds.id) as total_urls,
        (SELECT COUNT(*) FROM urls WHERE urls.seed_id = seeds.id AND urls.status = 'done') as done_urls
    FROM seeds
    ORDER BY seeds.id
    """
    cursor = conn.execute(query)
    return [tuple(row) for row in cursor]

def get_setting(conn, key):
    """Get the typed value from get_settings for the given key, or None if key is not in DEFAULT_SETTINGS."""
    settings = get_settings(conn)
    return settings.get(key)

def convert_setting_value(key, text: str):
    """Convert the text to the Python type of DEFAULT_SETTINGS[key]. Raise KeyError for an unknown key."""
    if key not in DEFAULT_SETTINGS:
        raise KeyError(key)
    default_type = type(DEFAULT_SETTINGS[key])
    if default_type is bool:
        if text.strip().lower() in ("1", "true", "yes"):
            return True
        elif text.strip().lower() in ("0", "false", "no"):
            return False
        else:
            raise ValueError(f"Invalid boolean value: {text}")
    elif default_type is int:
        return int(text)
    elif default_type is float:
        return float(text)
    else:
        return text

def get_stats(conn) -> dict:
    """Get stats including crawl_state and respect_robots."""
    stats_dict = stats(conn)
    settings = get_settings(conn)
    stats_dict["crawl_state"] = settings.get("crawl_state")
    stats_dict["respect_robots"] = settings.get("respect_robots", False)
    return stats_dict

def block_domain(conn, host):
    """Block a domain by setting its blocked status to 1."""
    conn.execute("INSERT INTO domains (host, blocked) VALUES (?, 1) ON CONFLICT(host) DO UPDATE SET blocked = 1", (host,))
    conn.commit()

def unblock_domain(conn, host):
    """Unblock a domain by setting its blocked status to 0."""
    conn.execute("UPDATE domains SET blocked = 0 WHERE host = ?", (host,))
    conn.commit()

def retry_errors(conn) -> int:
    """Retry errors by setting their status to 'queued' and resetting attempts."""
    cursor = conn.execute("""
    UPDATE urls
    SET status = 'queued', attempts = 0, next_attempt_at = NULL, error = NULL
    WHERE status = 'error'
    """)
    conn.commit()
    return cursor.rowcount

def get_urls(conn, status=None) -> list:
    """Get URLs with optional status filter."""
    query = "SELECT url, host, status, http_status, title, description, content_type, depth, fetched_at FROM urls"
    if status is not None:
        query += " WHERE status = ?"
    query += " ORDER BY id"
    cursor = conn.execute(query, (status,) if status is not None else ())
    return [tuple(row) for row in cursor]
