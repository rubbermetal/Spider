"""On admin start-up a leftover 'running'/'paused' crawl_state must not outlive the crawler.

The crawler runs as a thread inside the admin process, so after a restart nothing is
crawling even though the database still says 'running' (seen 2026-11-07).
"""
import pytest

from spiderlib import db, queue
from spiderlib.admin import create_app
from spiderlib.admin.runner import reset_stale_state

from conftest import FakeRunner, get_csrf


def state_of(path):
    conn = db.connect(path)
    try:
        return db.get_settings(conn)["crawl_state"]
    finally:
        conn.close()


def set_state(path, value):
    conn = db.connect(path)
    db.set_setting(conn, "crawl_state", value)
    conn.close()


def log_messages(path):
    conn = db.connect(path)
    try:
        return [r["message"] for r in conn.execute("SELECT message FROM log")]
    finally:
        conn.close()


@pytest.fixture
def dbpath(tmp_path):
    return str(tmp_path / "s.db")


# ---- reset_stale_state ---------------------------------------------------- #

def test_running_is_reset_to_stopped_when_no_crawler(dbpath):
    set_state(dbpath, "running")
    assert reset_stale_state(dbpath, FakeRunner()) is True
    assert state_of(dbpath) == "stopped"


def test_paused_is_reset_to_stopped_when_no_crawler(dbpath):
    set_state(dbpath, "paused")
    assert reset_stale_state(dbpath, FakeRunner()) is True
    assert state_of(dbpath) == "stopped"


def test_stopped_is_left_alone(dbpath):
    set_state(dbpath, "stopped")
    assert reset_stale_state(dbpath, FakeRunner()) is False
    assert state_of(dbpath) == "stopped"


def test_fresh_database_is_left_alone(dbpath):
    assert reset_stale_state(dbpath, FakeRunner()) is False
    assert state_of(dbpath) == "stopped"


def test_running_state_is_kept_when_a_crawler_is_really_running(dbpath):
    set_state(dbpath, "running")
    runner = FakeRunner()
    runner.started = True                      # is_running() -> True
    assert reset_stale_state(dbpath, runner) is False
    assert state_of(dbpath) == "running"


def test_reset_is_logged_once(dbpath):
    set_state(dbpath, "running")
    reset_stale_state(dbpath, FakeRunner())
    msgs = [m for m in log_messages(dbpath) if "reset" in m.lower()]
    assert len(msgs) == 1
    assert "running" in msgs[0]                # says what it was reset from
    reset_stale_state(dbpath, FakeRunner())    # second call: nothing to reset, nothing new logged
    assert len([m for m in log_messages(dbpath) if "reset" in m.lower()]) == 1


def test_no_log_entry_when_nothing_was_reset(dbpath):
    reset_stale_state(dbpath, FakeRunner())
    assert [m for m in log_messages(dbpath) if "reset" in m.lower()] == []


def test_other_settings_are_untouched(dbpath):
    conn = db.connect(dbpath)
    db.set_setting(conn, "respect_robots", False)
    db.set_setting(conn, "concurrency", 7)
    db.set_setting(conn, "crawl_state", "running")
    conn.close()
    reset_stale_state(dbpath, FakeRunner())
    conn = db.connect(dbpath)
    s = db.get_settings(conn)
    conn.close()
    assert s["respect_robots"] is False and s["concurrency"] == 7


def test_queue_rows_are_untouched(dbpath):
    conn = db.connect(dbpath)
    queue.enqueue(conn, "http://a.com/")
    conn.execute("UPDATE urls SET status = 'fetching'")
    conn.commit()
    db.set_setting(conn, "crawl_state", "running")
    conn.close()
    reset_stale_state(dbpath, FakeRunner())
    conn = db.connect(dbpath)
    assert conn.execute("SELECT status FROM urls").fetchone()[0] == "fetching"   # recover_stale handles it on Start
    conn.close()


# ---- create_app wiring --------------------------------------------------- #

def test_create_app_resets_a_stale_running_state(dbpath):
    set_state(dbpath, "running")
    create_app(dbpath, password="pw", secret_key="k", runner=FakeRunner())
    assert state_of(dbpath) == "stopped"


def test_dashboard_api_shows_stopped_after_restart(dbpath):
    set_state(dbpath, "running")
    app = create_app(dbpath, password="pw", secret_key="k", runner=FakeRunner())
    app.config["TESTING"] = True
    client = app.test_client()
    token = get_csrf(client)
    assert client.post("/login", data={"password": "pw", "csrf": token}).status_code == 302
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.get_json()
    assert data["crawl_state"] == "stopped"
    assert data["running"] is False


def test_create_app_leaves_a_running_crawler_alone(dbpath):
    set_state(dbpath, "running")
    runner = FakeRunner()
    runner.started = True
    create_app(dbpath, password="pw", secret_key="k", runner=runner)
    assert state_of(dbpath) == "running"
