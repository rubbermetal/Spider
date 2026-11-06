import re
from spiderlib import db
import pytest

def get_audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id")]

def token(client):
    response = client.get("/settings", follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

def test_settings_requires_login(admin_client):
    response = admin_client.get("/settings")
    assert response.status_code == 302

def test_settings_page_renders(client):
    response = client.get("/settings")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Politeness" in body
    assert "Limits" in body
    assert "Retries" in body
    assert "User-Agent" in body
    assert "Respect robots.txt" in body
    assert "Workers" in body
    assert "IGNORED" not in body

def test_settings_page_warns_when_robots_off(client, admin_db):
    db.set_setting(db.connect(admin_db), "respect_robots", False)
    response = client.get("/settings")
    body = response.get_data(as_text=True)
    assert "robots.txt is being IGNORED" in body
    assert 'name="respect_robots" checked' not in body

def test_save_settings(client, admin_db):
    data = {
        "csrf": token(client),
        "user_agent": "MyBot/2 (+http://me.org)",
        "respect_robots": "1",
        "default_delay": "1.5",
        "concurrency": "3",
        "timeout": "10",
        "max_bytes": "500000",
        "max_depth": "4",
        "max_pages_per_domain": "100",
        "max_retries": "1",
        "retry_backoff_seconds": "60"
    }
    response = client.post("/settings", data=data)
    assert response.status_code == 302
    settings = db.get_settings(db.connect(admin_db))
    assert settings["user_agent"] == "MyBot/2 (+http://me.org)"
    assert settings["default_delay"] == 1.5
    assert settings["concurrency"] == 3
    assert settings["max_depth"] == 4
    assert settings["respect_robots"] is True
    assert settings["allow_external"] is False
    audit_rows = get_audit(db.connect(admin_db))
    assert any(row["actor"] == "admin" for row in audit_rows)

def test_save_can_turn_robots_off(client, admin_db):
    data = {
        "csrf": token(client),
        "user_agent": "MyBot/2 (+http://me.org)",
        "respect_robots": "1",
        "default_delay": "1.5",
        "concurrency": "3",
        "timeout": "10",
        "max_bytes": "500000",
        "max_depth": "4",
        "max_pages_per_domain": "100",
        "max_retries": "1",
        "retry_backoff_seconds": "60"
    }
    response = client.post("/settings", data=data)
    assert response.status_code == 302
    settings = db.get_settings(db.connect(admin_db))
    assert settings["respect_robots"] is True
    data.pop("respect_robots")
    response = client.post("/settings", data=data)
    assert response.status_code == 302
    settings = db.get_settings(db.connect(admin_db))
    assert settings["respect_robots"] is False
    response = client.get("/settings")
    body = response.get_data(as_text=True)
    assert "robots.txt is being IGNORED" in body

def test_invalid_value_shows_error_and_keeps_old(client, admin_db):
    data = {
        "csrf": token(client),
        "concurrency": "999",
        "respect_robots": "1"
    }
    response = client.post("/settings", data=data)
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "must be between 1 and 32" in body
    assert "999" in body
    settings = db.get_settings(db.connect(admin_db))
    assert settings["concurrency"] == 4

def test_flash_message_after_save(client):
    data = {
        "csrf": token(client),
        "respect_robots": "1",
        "concurrency": "5"
    }
    response = client.post("/settings", data=data, follow_redirects=True)
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Saved 1 change" in body

def test_post_without_csrf_rejected(client):
    data = {
        "concurrency": "5"
    }
    response = client.post("/settings", data=data)
    assert response.status_code == 400
