"""Starts and tracks the crawler thread inside the admin process."""

import threading
from spiderlib import db
from spiderlib.crawler import Crawler


def reset_stale_state(db_path, runner) -> bool:
    """Set a leftover 'running'/'paused' crawl_state back to 'stopped' when no crawler is running.

    The crawler is a thread inside the admin process, so after a restart nothing is
    crawling even though the database still says so. Returns True when it reset the state.
    """
    if runner.is_running():
        return False
    conn = db.connect(db_path)
    try:
        state = db.get_settings(conn)["crawl_state"]
        if state not in ("running", "paused"):
            return False
        db.set_setting(conn, "crawl_state", "stopped")
        db.log_event(conn, "info", f"crawl state reset to stopped at startup (was {state}; no crawler was running)")
        return True
    finally:
        conn.close()

class Runner:
    def __init__(self, factory=Crawler):
        self._factory = factory
        self._thread = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, db_path, exit_when_idle=True) -> bool:
        with self._lock:
            if self.is_running():
                return False
            crawler = self._factory(db_path)
            self._thread = threading.Thread(target=crawler.run, kwargs={"exit_when_idle": exit_when_idle})
            self._thread.daemon = True
            self._thread.start()
            return True

    def join(self, timeout=None):
        if self._thread:
            self._thread.join(timeout)
