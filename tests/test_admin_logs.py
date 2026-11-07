import re
from spiderlib import db

def conn_of(admin_db):
    return db.connect(admin_db)

def token(client, path="/logs"):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

def test_requires_login(admin_client):
    response = admin_client.get("/logs")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = admin_client.get("/audit")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_empty_logs_page(client):
    response = client.get("/logs")
    assert response.status_code == 200
    assert "No log entries" in response.get_data(as_text=True)
    assert "Event log" in response.get_data(as_text=True)
    assert "The audit log is never deleted" in response.get_data(as_text=True)

def test_logs_listed_and_filtered(client, admin_db):
    conn = conn_of(admin_db)
    db.log_event(conn, "info", "crawl started")
    db.log_event(conn, "error", "http://a.com/x: boom")

    response = client.get("/logs")
    assert response.status_code == 200
    assert "crawl started" in response.get_data(as_text=True)
    assert "boom" in response.get_data(as_text=True)
    assert "2 entries" in response.get_data(as_text=True)

    response = client.get("/logs?level=error")
    assert response.status_code == 200
    assert "boom" in response.get_data(as_text=True)
    assert "crawl started" not in response.get_data(as_text=True)

    response = client.get("/logs?q=started")
    assert response.status_code == 200
    assert "crawl started" in response.get_data(as_text=True)
    assert "boom" not in response.get_data(as_text=True)

    response = client.get("/logs?level=bogus&page=zzz&per_page=9")
    assert response.status_code == 200

def test_logs_pagination(client, admin_db):
    conn = conn_of(admin_db)
    for i in range(60):
        db.log_event(conn, "info", f"event {i}")

    response = client.get("/logs?per_page=25")
    assert response.status_code == 200
    assert "Page 1 of 3" in response.get_data(as_text=True)
    assert "Next" in response.get_data(as_text=True)
    assert "Prev" not in response.get_data(as_text=True)

    response = client.get("/logs?per_page=25&page=2&level=info")
    assert response.status_code == 200
    assert "Page 2 of 3" in response.get_data(as_text=True)
    assert "Prev" in response.get_data(as_text=True)
    assert "level=info" in response.get_data(as_text=True)

def test_prune_logs(client, admin_db):
    conn = conn_of(admin_db)
    conn.execute("INSERT INTO log (ts, level, message) VALUES ('2000-01-01T00:00:00Z', 'info', 'old log')")
    conn.commit()
    db.log_event(conn, "info", "new log")

    csrf_token = token(client)
    response = client.post("/logs/prune", data={"csrf": csrf_token, "days": "30"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Deleted 1 log entries." in response.get_data(as_text=True)

    response = client.get("/logs")
    assert response.status_code == 200
    assert "new log" in response.get_data(as_text=True)
    assert "old log" not in response.get_data(as_text=True)

    response = client.post("/logs/prune", data={"csrf": csrf_token, "days": "abc"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Choose a valid number of days." in response.get_data(as_text=True)

    response = client.post("/logs/prune", data={"csrf": csrf_token, "days": "0"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Choose a valid number of days." in response.get_data(as_text=True)

def test_prune_requires_csrf(client):
    response = client.post("/logs/prune", data={"days": "30"})
    assert response.status_code == 400

def test_audit_page(client, admin_db):
    conn = conn_of(admin_db)
    db.audit(conn, "admin", "seed_add", "http://a.com/")
    db.audit(conn, "cli", "stop", "")

    response = client.get("/audit")
    assert response.status_code == 200
    assert "Audit log" in response.get_data(as_text=True)
    assert "seed_add" in response.get_data(as_text=True)
    assert "http://a.com/" in response.get_data(as_text=True)
    assert "cli" in response.get_data(as_text=True)
    assert "2 entries" in response.get_data(as_text=True)
    assert "admin" in response.get_data(as_text=True)
    assert "cli" in response.get_data(as_text=True)

    response = client.get("/audit?actor=cli")
    assert response.status_code == 200
    assert "stop" in response.get_data(as_text=True)
    assert "http://a.com/" not in response.get_data(as_text=True)  # detail of the admin entry (the dropdown still lists the action name)

    response = client.get("/audit?q=a.com")
    assert response.status_code == 200
    assert "seed_add" in response.get_data(as_text=True)
    assert "<td>stop</td>" not in response.get_data(as_text=True)

def test_audit_empty(client):
    response = client.get("/audit")
    assert response.status_code == 200
    assert "No audit entries" in response.get_data(as_text=True)

def test_nav_links(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/logs"' in response.get_data(as_text=True)
    assert 'href="/audit"' in response.get_data(as_text=True)
    assert 'href="/export"' in response.get_data(as_text=True)
