import re
import pytest
from spiderlib.admin import create_app

def test_no_password_returns_503(admin_db):
    app = create_app(admin_db, password="", secret_key="k")
    client = app.test_client()
    response = client.get("/login")
    assert response.status_code == 503
    response = client.get("/")
    assert response.status_code == 503

def test_unauthenticated_redirects_to_login(admin_client):
    response = admin_client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    response = admin_client.get("/api/stats")
    assert response.status_code == 401
    assert response.get_json() == {"error": "login required"}

def test_login_page_has_csrf(admin_client):
    response = admin_client.get("/login")
    assert response.status_code == 200
    assert 'name="csrf"' in response.text

def test_wrong_password(admin_client, csrf):
    response = admin_client.post("/login", data={"password": "nope", "csrf": csrf()})
    assert response.status_code == 401
    assert "Invalid password" in response.text

def test_correct_password_logs_in(admin_client, csrf):
    response = admin_client.post("/login", data={"password": "pw", "csrf": csrf()})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    response = admin_client.get("/")
    assert response.status_code == 200

def test_post_without_csrf_rejected(admin_client):
    response = admin_client.get("/login")
    response = admin_client.post("/login", data={"password": "pw"})
    assert response.status_code == 400

def test_lockout_after_five_failures(admin_client, csrf):
    for _ in range(5):
        response = admin_client.post("/login", data={"password": "nope", "csrf": csrf()})
        assert response.status_code == 401
    response = admin_client.post("/login", data={"password": "pw", "csrf": csrf()})
    assert response.status_code == 429

def test_next_redirect_is_local_only(admin_client, csrf):
    response = admin_client.post("/login?next=//evil.com", data={"password": "pw", "csrf": csrf()})
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    client = admin_client.application.test_client()
    token = re.search(r'name="csrf" value="([^"]+)"', client.get("/login").get_data(as_text=True)).group(1)
    response = client.post("/login?next=/api/stats", data={"password": "pw", "csrf": token})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/api/stats")

def test_logout(logged_in, page_csrf):
    response = logged_in.post("/logout", data={"csrf": page_csrf()})
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    response = logged_in.get("/")
    assert response.status_code == 302

def test_post_when_logged_out_without_session_csrf(admin_client):
    response = admin_client.post("/logout")
    assert response.status_code == 400
