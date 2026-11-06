import pytest
from spiderlib import cli

class FakeApp:
    runs = []
    created = []

    def __init__(self):
        pass

    def run(self, host, port, threaded):
        self.runs.append((host, port, threaded))

def fake_create(db_path, password=None, trust_proxy=False, **kw):
    FakeApp.created.append((db_path, password, trust_proxy))
    return FakeApp()

def patch_app(monkeypatch):
    FakeApp.runs.clear()
    FakeApp.created.clear()
    monkeypatch.setattr("spiderlib.admin.create_app", fake_create)

@pytest.fixture
def dbp(tmp_path):
    return str(tmp_path / "t.db")

def test_serve_runs_app_with_options(dbp, monkeypatch, capsys):
    patch_app(monkeypatch)
    monkeypatch.delenv("SPIDER_ADMIN_PASSWORD", raising=False)
    assert cli.main(["--db", dbp, "serve", "--host", "0.0.0.0", "--port", "9001", "--password", "pw", "--trust-proxy"]) == 0
    assert FakeApp.created == [(dbp, "pw", True)]
    assert FakeApp.runs == [("0.0.0.0", 9001, True)]
    captured = capsys.readouterr()
    assert "http://0.0.0.0:9001/" in captured.out

def test_serve_defaults(dbp, monkeypatch):
    patch_app(monkeypatch)
    monkeypatch.setenv("SPIDER_ADMIN_PASSWORD", "envpw")
    assert cli.main(["--db", dbp, "serve"]) == 0
    assert FakeApp.created == [(dbp, "envpw", False)]
    assert FakeApp.runs == [("127.0.0.1", 8080, True)]

def test_serve_without_password_fails(dbp, monkeypatch, capsys):
    patch_app(monkeypatch)
    monkeypatch.delenv("SPIDER_ADMIN_PASSWORD", raising=False)
    assert cli.main(["--db", dbp, "serve"]) == 2
    captured = capsys.readouterr()
    assert "no admin password" in captured.err
    assert FakeApp.runs == []
