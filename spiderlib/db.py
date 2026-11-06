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
