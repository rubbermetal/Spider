"""
Module to check if a web crawler may fetch a URL according to robots.txt.
Usage example:
    from spiderlib import db, robots
    conn = db.connect("spider.db")
    url = "http://example.com"
    settings = db.get_settings(conn)
    if robots.allowed(conn, url, settings):
        print("Crawling allowed")
    else:
        print("Crawling not allowed")
"""

import urllib.request
import urllib.error
import urllib.robotparser
import urllib.parse
import datetime
from spiderlib import db
from spiderlib.urls import host_of

MAX_ROBOTS_BYTES = 512000
FRESH_HOURS = 24
RETRY_HOURS = 1

def fetch_robots_txt(url: str, user_agent: str, timeout: float) -> tuple:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_ROBOTS_BYTES).decode("utf-8", errors="replace")
            return (response.status, body)
    except urllib.error.HTTPError as e:
        return (e.code, "")
    except Exception:
        return (None, "")

def parse_robots(status, text: str) -> urllib.robotparser.RobotFileParser:
    rp = urllib.robotparser.RobotFileParser()
    if status is None:
        rp.disallow_all = True
    elif status == 200:
        rp.parse(text.splitlines())
    elif status in (401, 403):
        rp.disallow_all = True
    elif status >= 500:
        rp.disallow_all = True
    else:
        rp.allow_all = True
    rp.modified()
    return rp

def _parse_ts(ts: str) -> datetime.datetime:
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)

def get_robots(conn, url: str, settings: dict, fetcher=fetch_robots_txt) -> urllib.robotparser.RobotFileParser:
    host = host_of(url)
    parts = urllib.parse.urlsplit(url)
    scheme, netloc = parts.scheme, parts.netloc.rpartition("@")[2]
    cursor = conn.execute("INSERT OR IGNORE INTO domains (host) VALUES (?)", (host,))
    cursor.execute("SELECT robots_txt, robots_status, robots_fetched_at FROM domains WHERE host = ?", (host,))
    row = cursor.fetchone()
    if row:
        robots_txt, robots_status, robots_fetched_at = row
        if robots_fetched_at is not None:
            fetched_at = _parse_ts(robots_fetched_at)
            limit = RETRY_HOURS if (robots_status is None or robots_status >= 500) else FRESH_HOURS
            if (datetime.datetime.now(datetime.timezone.utc) - fetched_at).total_seconds() / 3600 < limit:
                return parse_robots(robots_status, robots_txt or "")
    status, text = fetcher(f"{scheme}://{netloc}/robots.txt", settings["user_agent"], settings["timeout"])
    conn.execute("UPDATE domains SET robots_txt = ?, robots_status = ?, robots_fetched_at = ? WHERE host = ?", (text, status, db.now(), host))
    conn.commit()
    return parse_robots(status, text or "")

def allowed(conn, url: str, settings: dict, fetcher=fetch_robots_txt) -> bool:
    if not settings["respect_robots"]:
        return True
    return get_robots(conn, url, settings, fetcher).can_fetch(settings["user_agent"], url)

def crawl_delay(conn, url: str, settings: dict, fetcher=fetch_robots_txt) -> float:
    host = host_of(url)
    cursor = conn.execute("SELECT delay_override FROM domains WHERE host = ?", (host,))
    row = cursor.fetchone()
    if row and row[0] is not None:
        return float(row[0])
    delay = float(settings["default_delay"])
    if settings["respect_robots"]:
        rd = get_robots(conn, url, settings, fetcher).crawl_delay(settings["user_agent"])
        if rd is not None and float(rd) > delay:
            delay = float(rd)
    return delay
