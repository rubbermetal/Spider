"""
Crawl engine for a web crawler. Ties together the other modules.

Usage example:
    from spiderlib.crawler import Crawler
    crawler = Crawler("path/to/database.db")
    crawler.run()
"""

import time
import threading
from spiderlib import db, fetch, robots, parse, queue
from spiderlib.urls import host_of, normalize_url, is_same_site, registered_domain

def _domain_blocked(conn, host):
    """Check if a domain is blocked."""
    query = "SELECT 1 FROM domains WHERE blocked = 1 AND (host = ? OR host = ?)"
    return conn.execute(query, (host, registered_domain(host))).fetchone() is not None

def _redirect_problem(conn, row, final_url, settings):
    """Check for redirect problems."""
    final = normalize_url(final_url)
    if final is None or final == row["url"] or host_of(final) == row["host"]:
        return None
    if _domain_blocked(conn, host_of(final)):
        return "redirect to blocked domain"
    if row["seed_id"] is not None:
        seed = conn.execute("SELECT * FROM seeds WHERE id = ?", (row["seed_id"],)).fetchone()
        if seed is not None:
            allow_external = bool(seed["allow_external"]) if seed["allow_external"] is not None else settings["allow_external"]
            if not allow_external and not is_same_site(final, seed["url"]):
                return "redirect out of scope"
    return None

def process_one(conn, row, settings, throttle, fetcher=fetch.fetch, robots_fetcher=robots.fetch_robots_txt):
    """Process one claimed URL."""
    try:
        url = row["url"]
        host = row["host"]
        if _domain_blocked(conn, host):
            queue.set_status(conn, row["id"], "blocked", "domain blocked")
            return "blocked"
        if not robots.allowed(conn, url, settings, robots_fetcher):
            queue.set_status(conn, row["id"], "blocked", "robots.txt")
            return "blocked"
        delay = robots.crawl_delay(conn, url, settings, robots_fetcher)
        throttle.wait(host, delay)
        result = fetcher(url, settings)
        if not result["ok"]:
            return queue.record_failure(conn, row["id"], result, settings)
        problem = _redirect_problem(conn, row, result["final_url"], settings)
        if problem:
            queue.set_status(conn, row["id"], "skipped", problem)
            return "skipped"
        if result["skipped_reason"]:
            queue.record_result(conn, row["id"], result, None, None)
            return "done"
        html = parse.decode_body(result["body"], result["content_type"])
        parsed = parse.parse_html(html, result["final_url"])
        digest = parse.content_hash(html)
        # Queue the links BEFORE marking this row done: while it is still
        # 'fetching' an idle worker cannot see an empty queue and stop early.
        if not parsed["nofollow"]:
            queue.add_links(conn, row["id"], parsed["links"], row["seed_id"], row["depth"], settings)
        queue.record_result(conn, row["id"], result, parsed, digest)
        return "done"
    except Exception as exc:
        db.log_event(conn, "error", f"{row['url']}: {exc}")
        return queue.record_failure(conn, row["id"], {"status": None, "error": str(exc), "error_kind": "other", "elapsed_ms": 0}, settings)

def pause(conn):
    """Pause the crawler."""
    db.set_setting(conn, "crawl_state", "paused")

def resume(conn):
    """Resume the crawler."""
    db.set_setting(conn, "crawl_state", "running")

def request_stop(conn):
    """Request the crawler to stop."""
    db.set_setting(conn, "crawl_state", "stopped")

class Crawler:
    def __init__(self, db_path, fetcher=fetch.fetch, robots_fetcher=robots.fetch_robots_txt, idle_sleep=0.5):
        self.db_path = db_path
        self.fetcher = fetcher
        self.robots_fetcher = robots_fetcher
        self.idle_sleep = idle_sleep
        self.throttle = fetch.HostThrottle()
        self.exit_when_idle = True

    def run(self, exit_when_idle=True):
        """Run the crawler."""
        self.exit_when_idle = exit_when_idle
        conn = db.connect(self.db_path)
        queue.recover_stale(conn)
        db.set_setting(conn, "crawl_state", "running")
        db.log_event(conn, "info", "crawl started")
        n = max(1, db.get_settings(conn)["concurrency"])
        threads = []
        for _ in range(n):
            thread = threading.Thread(target=self._worker, daemon=True)
            thread.start()
            threads.append(thread)
        try:
            for thread in threads:
                thread.join()
        except KeyboardInterrupt:
            request_stop(conn)
            for thread in threads:
                thread.join()
        finally:
            db.set_setting(conn, "crawl_state", "stopped")
            db.log_event(conn, "info", "crawl stopped")
            conn.close()

    def _worker(self):
        """Worker function for the crawler."""
        conn = db.connect(self.db_path)
        try:
            while True:
                try:
                    settings = db.get_settings(conn)
                    state = settings["crawl_state"]
                    if state == "stopped":
                        break
                    if state == "paused":
                        time.sleep(self.idle_sleep)
                        continue
                    row = queue.claim_next(conn)
                    if row is None:
                        count = conn.execute("SELECT COUNT(*) FROM urls WHERE status IN ('queued','fetching')").fetchone()[0]
                        if count == 0 and self.exit_when_idle:
                            db.set_setting(conn, "crawl_state", "stopped")
                            break
                        else:
                            time.sleep(self.idle_sleep)
                            continue
                    process_one(conn, row, settings, self.throttle, self.fetcher, self.robots_fetcher)
                except Exception as exc:
                    db.log_event(conn, "error", f"worker error: {exc}")
                    time.sleep(self.idle_sleep)
        finally:
            conn.close()
