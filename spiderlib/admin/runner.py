"""Starts and tracks the crawler thread inside the admin process."""

import threading
from spiderlib.crawler import Crawler

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
