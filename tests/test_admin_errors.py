import re
from spiderlib import db

def conn_of(admin_db):
    return db.connect(admin_db)

def token(client, path="/errors"):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

def add(admin_db, url, host="a.com", status="error", http_status=None, error=None):
    conn = conn_of(admin_db)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO urls (url, host, status, http_status, error, added_at, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (url, host, status, http_status, error, db.now(), db.now())
    )
    conn.commit()
    return cursor.lastrowid

def status_of(admin_db, id):
    conn = conn_of(admin_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM urls WHERE id = ?", (id,))
    result = cursor.fetchone()
    return result[0] if result else None

def test_requires_login(admin_client):
    response = admin_client.get("/errors")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    response = admin_client.get("/errors/timeout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

def test_empty_page(client):
    response = client.get("/errors")
    assert response.status_code == 200
    assert "No problems" in response.get_data(as_text=True)
    assert "0 URL(s)" in response.get_data(as_text=True)

def test_groups_listed(client, admin_db):
    timeout1_id = add(admin_db, "http://example.com/timeout1", error="timed out")
    timeout2_id = add(admin_db, "http://example.com/timeout2", error="timed out")
    http404_id = add(admin_db, "http://b.org/404", http_status=404, error="HTTP 404", host="b.org")
    blocked_id = add(admin_db, "http://example.com/blocked", status="blocked", error="robots.txt")

    response = client.get("/errors")
    assert response.status_code == 200
    assert "Timeouts" in response.get_data(as_text=True)
    assert "HTTP 404" in response.get_data(as_text=True)
    assert "Blocked by robots.txt" in response.get_data(as_text=True)
    assert "4 URL(s)" in response.get_data(as_text=True)
    assert 'href="/errors/timeout"' in response.get_data(as_text=True)
    assert 'href="/domains/a.com"' in response.get_data(as_text=True)
    assert 'Retry all' in response.get_data(as_text=True)

def test_group_page(client, admin_db):
    timeout_id = add(admin_db, "http://example.com/timeout", error="timed out")
    http404_id = add(admin_db, "http://example.com/404", http_status=404, error="HTTP 404")

    response = client.get("/errors/timeout")
    assert response.status_code == 200
    assert "Timeouts" in response.get_data(as_text=True)
    assert "http://example.com/timeout" in response.get_data(as_text=True)
    assert "http://example.com/404" not in response.get_data(as_text=True)

    response = client.get("/errors/http-404")
    assert response.status_code == 200
    assert "HTTP 404" in response.get_data(as_text=True)

    response = client.get("/errors/nope")
    assert response.status_code == 404

    response = client.get("/errors/dns")
    assert response.status_code == 200
    assert "Nothing here" in response.get_data(as_text=True)

def test_retry_all(client, admin_db):
    timeout1_id = add(admin_db, "http://example.com/timeout1", error="timed out")
    timeout2_id = add(admin_db, "http://example.com/timeout2", error="timed out")
    http404_id = add(admin_db, "http://example.com/404", http_status=404, error="HTTP 404")

    csrf_token = token(client, "/errors")
    response = client.post("/errors/timeout/retry-all", data={"csrf": csrf_token}, follow_redirects=True)
    assert response.status_code == 200
    assert "Requeued 2 URL(s)." in response.get_data(as_text=True)
    assert status_of(admin_db, timeout1_id) == "queued"
    assert status_of(admin_db, timeout2_id) == "queued"
    assert status_of(admin_db, http404_id) == "error"

    csrf_token = token(client, "/errors")
    response = client.post("/errors/nope/retry-all", data={"csrf": csrf_token}, follow_redirects=True)
    assert response.status_code == 404

def test_retry_selected(client, admin_db):
    timeout1_id = add(admin_db, "http://example.com/timeout1", error="timed out")
    timeout2_id = add(admin_db, "http://example.com/timeout2", error="timed out")

    csrf_token = token(client, "/errors/timeout")
    response = client.post("/errors/retry", data={"csrf": csrf_token, "ids": [timeout1_id], "next": "/errors/timeout"}, follow_redirects=True)
    assert response.status_code == 200
    assert "Requeued 1 URL(s)." in response.get_data(as_text=True)
    assert status_of(admin_db, timeout1_id) == "queued"
    assert status_of(admin_db, timeout2_id) == "error"

def test_next_is_restricted(client, admin_db):
    csrf_token = token(client, "/errors")
    response = client.post("/errors/retry", data={"csrf": csrf_token, "ids": [1], "next": "http://evil.com/"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/errors"

    csrf_token = token(client, "/errors")
    response = client.post("/errors/retry", data={"csrf": csrf_token, "ids": [1], "next": "/errors/timeout"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/errors/timeout"

    csrf_token = token(client, "/errors")
    response = client.post("/errors/retry", data={"csrf": csrf_token, "ids": [1], "next": "//evil.com"})
    assert response.status_code == 302
    assert response.headers["Location"] == "/errors"

def test_retry_selected_without_ids(client, admin_db):
    csrf_token = token(client, "/errors")
    response = client.post("/errors/retry", data={"csrf": csrf_token}, follow_redirects=True)
    assert response.status_code == 200
    assert "nothing selected" in response.get_data(as_text=True)

def test_csrf_required(client, admin_db):
    response = client.post("/errors/timeout/retry-all", follow_redirects=True)
    assert response.status_code == 400

    response = client.post("/errors/retry", follow_redirects=True)
    assert response.status_code == 400

def test_nav_has_errors_link(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="/errors"' in response.get_data(as_text=True)
