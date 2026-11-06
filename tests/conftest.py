import re
import pytest
from spiderlib import db
from spiderlib.admin import create_app, auth

class FakeRunner:
    def __init__(self):
        self.calls = []
        self.started = False

    def start(self, db_path, exit_when_idle=True):
        self.calls.append((db_path, exit_when_idle))
        if self.started:
            return False
        self.started = True
        return True

    def is_running(self):
        return self.started

    def join(self, timeout=None):
        pass

@pytest.fixture
def admin_db(tmp_path):
    return str(tmp_path / "admin.db")

@pytest.fixture(autouse=True)
def clear_login_failures():
    auth.FAILS.clear()
    yield
    auth.FAILS.clear()

@pytest.fixture
def admin_app(admin_db):
    runner = FakeRunner()
    app = create_app(admin_db, password="pw", secret_key="test-key", runner=runner)
    app.config["TESTING"] = True
    return app

@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()

def get_csrf(client, path="/login"):
    response = client.get(path, follow_redirects=True)
    match = re.search(r'name="csrf" value="([^"]+)"', response.get_data(as_text=True))
    if match:
        return match.group(1)
    return None

@pytest.fixture
def csrf(admin_client):
    def token(path="/login"):
        return get_csrf(admin_client, path)
    return token

@pytest.fixture
def logged_in(admin_client):
    token = get_csrf(admin_client)
    response = admin_client.post("/login", data={"password": "pw", "csrf": token})
    assert response.status_code == 302
    return admin_client

@pytest.fixture
def page_csrf(logged_in):
    def token():
        return get_csrf(logged_in, "/")
    return token

@pytest.fixture
def client(logged_in):
    """Alias used by the dashboard tests: a logged-in test client."""
    return logged_in
