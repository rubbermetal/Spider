import pytest
from datetime import datetime, timezone
from spiderlib import db

def conn_of(admin_db):
    return db.connect(admin_db)

def add_urls(conn, rows):
    for url, host, status, fetched_at in rows:
        conn.execute(
            "INSERT INTO urls (url, host, status, fetched_at, added_at) VALUES (?, ?, ?, ?, ?)",
            (url, host, status, fetched_at, db.now())
        )
    conn.commit()

@pytest.mark.usefixtures("logged_in")
def test_dashboard_renders(logged_in, client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Dashboard" in response.data
    assert b"Queued" in response.data
    assert b"Fetching" in response.data
    assert b"robots.txt: respected" in response.data
    assert b"Nothing logged yet." in response.data

@pytest.mark.usefixtures("logged_in", "admin_db")
def test_dashboard_warns_when_robots_ignored(logged_in, admin_db, client):
    conn = conn_of(admin_db)
    db.set_setting(conn, "respect_robots", False)
    response = client.get("/")
    assert b"robots.txt: IGNORED" in response.data

@pytest.mark.usefixtures("logged_in", "admin_db")
def test_api_stats_counts(logged_in, admin_db, client):
    conn = conn_of(admin_db)
    add_urls(conn, [
        ("http://a.com/1", "a.com", "done", None),
        ("http://a.com/2", "a.com", "queued", None),
        ("http://b.com/1", "b.com", "error", None),
        ("http://b.com/2", "b.com", "queued", None),
    ])
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.get_json()
    expected = {
        "total_urls": 4,
        "domains": 2,
        "queued": 2,
        "done": 1,
        "errors": 1,
        "fetching": 0,
        "running": False,
        "crawl_state": "stopped",
        "respect_robots": True,
    }
    assert {k: data[k] for k in expected} == expected

@pytest.mark.usefixtures("logged_in", "admin_db")
def test_pages_per_min(logged_in, admin_db, client):
    conn = conn_of(admin_db)
    now = db.now()
    add_urls(conn, [
        ("http://a.com/1", "a.com", "done", now),
        ("http://a.com/2", "a.com", "done", now),
        ("http://a.com/3", "a.com", "done", now),
        ("http://a.com/4", "a.com", "done", now),
        ("http://a.com/5", "a.com", "done", now),
        ("http://a.com/6", "a.com", "done", now),
        ("http://a.com/7", "a.com", "done", now),
        ("http://a.com/8", "a.com", "done", now),
        ("http://a.com/9", "a.com", "done", now),
        ("http://a.com/10", "a.com", "done", now),
        ("http://a.com/11", "a.com", "done", "2000-01-01T00:00:00Z"),
        ("http://a.com/12", "a.com", "done", "2000-01-01T00:00:00Z"),
        ("http://a.com/13", "a.com", "done", "2000-01-01T00:00:00Z"),
    ])
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.get_json()
    assert data["pages_per_min"] == 2.0

@pytest.mark.usefixtures("logged_in", "admin_db")
def test_recent_log_shown(logged_in, admin_db, client):
    conn = conn_of(admin_db)
    db.log_event(conn, "error", "something broke")
    response = client.get("/")
    assert response.status_code == 200
    assert b"something broke" in response.data
    assert b"Nothing logged yet." not in response.data

@pytest.mark.usefixtures("logged_in", "page_csrf", "admin_app", "admin_db")
def test_control_start(logged_in, page_csrf, admin_app, admin_db, client):
    response = client.post("/control/start", data={"csrf": page_csrf()})
    assert response.status_code == 302
    runner = admin_app.extensions["spider_runner"]
    assert len(runner.calls) == 1
    assert runner.calls[0][0] == admin_db
    conn = conn_of(admin_db)
    audit_rows = conn.execute("SELECT * FROM audit").fetchall()
    assert len(audit_rows) == 1
    assert audit_rows[0]["actor"] == "admin"
    assert audit_rows[0]["action"] == "start"
    assert audit_rows[0]["detail"] == "started"
    response = client.post("/control/start", data={"csrf": page_csrf()})
    assert response.status_code == 302
    audit_rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    assert audit_rows["detail"] == "already running"

@pytest.mark.usefixtures("logged_in", "page_csrf", "admin_db")
def test_control_pause_resume_stop(logged_in, page_csrf, admin_db, client):
    response = client.post("/control/pause", data={"csrf": page_csrf()})
    assert response.status_code == 302
    conn = conn_of(admin_db)
    settings = db.get_settings(conn)
    assert settings["crawl_state"] == "paused"
    response = client.post("/control/resume", data={"csrf": page_csrf()})
    assert response.status_code == 302
    settings = db.get_settings(conn)
    assert settings["crawl_state"] == "running"
    response = client.post("/control/stop", data={"csrf": page_csrf()})
    assert response.status_code == 302
    settings = db.get_settings(conn)
    assert settings["crawl_state"] == "stopped"
    audit_rows = conn.execute("SELECT * FROM audit").fetchall()
    assert len(audit_rows) == 3
    assert audit_rows[0]["action"] == "pause"
    assert audit_rows[1]["action"] == "resume"
    assert audit_rows[2]["action"] == "stop"

@pytest.mark.usefixtures("logged_in", "page_csrf")
def test_control_unknown_action(logged_in, page_csrf, client):
    response = client.post("/control/explode", data={"csrf": page_csrf()})
    assert response.status_code == 404

@pytest.mark.usefixtures("logged_in")
def test_control_requires_post(logged_in, client):
    response = client.get("/control/start")
    assert response.status_code == 405

@pytest.mark.usefixtures("admin_client")
def test_control_requires_login(admin_client):
    response = admin_client.post("/control/stop", data={"csrf": "x"})
    assert response.status_code == 400


def test_control_start_keep_running_passes_flag(logged_in, page_csrf, admin_app, admin_db):
    r = logged_in.post("/control/start", data={"csrf": page_csrf(), "forever": "yes"})
    assert r.status_code == 302
    runner = admin_app.extensions["spider_runner"]
    assert runner.calls == [(admin_db, False)]
    rows = [dict(x) for x in conn_of(admin_db).execute("SELECT * FROM audit ORDER BY id")]
    assert rows[-1]["detail"] == "started (keep running)"


def test_control_start_default_is_one_shot(logged_in, page_csrf, admin_app, admin_db):
    logged_in.post("/control/start", data={"csrf": page_csrf()})
    assert admin_app.extensions["spider_runner"].calls == [(admin_db, True)]


def test_dashboard_start_form_has_keep_running_checkbox(logged_in):
    assert 'name="forever"' in logged_in.get("/").get_data(as_text=True)
