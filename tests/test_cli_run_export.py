import csv
import io
import json
import pytest
from spiderlib import cli, db

@pytest.fixture
def dbp(tmp_path):
    return str(tmp_path / "t.db")

def run(dbp, *args):
    return cli.main(["--db", dbp, *args])

def prepare(dbp):
    run(dbp, "seed", "add", "http://a.com")
    conn = db.connect(dbp)
    conn.executescript("""
        UPDATE urls SET status='done', http_status=200, title='Home, "x"', description='D', content_type='text/html', fetched_at='2026-11-05T10:00:00Z' WHERE url='http://a.com/';
        INSERT INTO urls (url, host, status, added_at) VALUES ('http://a.com/p1','a.com','queued','2026-11-05T09:00:00Z');
    """)
    conn.commit()

class FakeCrawler:
    instances = []
    def __init__(self, db_path):
        self.db_path = db_path
        self.exit_when_idle = None
        FakeCrawler.instances.append(self)
    
    def run(self, exit_when_idle=True):
        self.exit_when_idle = exit_when_idle

@pytest.fixture(autouse=True)
def clear_fake_crawler():
    FakeCrawler.instances.clear()

def test_run_applies_options(dbp, capsys, monkeypatch):
    monkeypatch.setattr(cli, "Crawler", FakeCrawler)
    assert run(dbp, "run", "--concurrency", "6", "--delay", "0.5", "--ignore-robots") == 0
    captured = capsys.readouterr()
    assert "robots.txt: IGNORED" in captured.out
    settings = db.get_settings(db.connect(dbp))
    assert (settings["concurrency"], settings["default_delay"], settings["respect_robots"]) == (6, 0.5, False)
    assert len(FakeCrawler.instances) == 1
    assert FakeCrawler.instances[0].db_path == dbp
    assert FakeCrawler.instances[0].exit_when_idle is True

def test_run_forever_and_respect(dbp, capsys, monkeypatch):
    monkeypatch.setattr(cli, "Crawler", FakeCrawler)
    run(dbp, "config", "respect_robots", "false")
    assert run(dbp, "run", "--forever", "--respect-robots") == 0
    captured = capsys.readouterr()
    assert "robots.txt: respected" in captured.out
    settings = db.get_settings(db.connect(dbp))
    assert settings["respect_robots"] is True
    assert len(FakeCrawler.instances) == 1
    assert FakeCrawler.instances[0].db_path == dbp
    assert FakeCrawler.instances[0].exit_when_idle is False

def test_run_without_options_changes_nothing(dbp, capsys, monkeypatch):
    monkeypatch.setattr(cli, "Crawler", FakeCrawler)
    assert run(dbp, "run") == 0
    settings = db.get_settings(db.connect(dbp))
    default_settings = db.DEFAULT_SETTINGS
    assert all(settings[key] == default_settings[key] for key in default_settings if key != "crawl_state")

def test_run_flags_are_exclusive(dbp, monkeypatch):
    monkeypatch.setattr(cli, "Crawler", FakeCrawler)
    with pytest.raises(SystemExit) as excinfo:
        run(dbp, "run", "--ignore-robots", "--respect-robots")
    assert excinfo.value.code == 2

def test_export_csv_stdout(dbp, capsys):
    prepare(dbp)
    capsys.readouterr()
    assert run(dbp, "export") == 0
    captured = capsys.readouterr()
    out = captured.out
    reader = csv.DictReader(io.StringIO(out))
    rows = list(reader)
    assert len(rows) == 2
    assert rows[0] == {
        "url": "http://a.com/",
        "host": "a.com",
        "status": "done",
        "http_status": "200",
        "title": 'Home, "x"',
        "description": "D",
        "content_type": "text/html",
        "depth": "0",
        "fetched_at": "2026-11-05T10:00:00Z"
    }
    assert reader.fieldnames == ["url", "host", "status", "http_status", "title", "description", "content_type", "depth", "fetched_at"]

def test_export_json_status_filter(dbp, capsys):
    prepare(dbp)
    capsys.readouterr()
    assert run(dbp, "export", "--format", "json", "--status", "queued") == 0
    captured = capsys.readouterr()
    out = captured.out
    data = json.loads(out)
    assert len(data) == 1
    assert data[0]["url"] == "http://a.com/p1"

def test_export_to_file(dbp, tmp_path, capsys):
    prepare(dbp)
    capsys.readouterr()
    output_file = tmp_path / "o.json"
    assert run(dbp, "export", "--format", "json", "--out", str(output_file)) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    with open(output_file, "r") as f:
        data = json.load(f)
    assert len(data) == 2

def test_no_command_exits(dbp):
    with pytest.raises(SystemExit) as excinfo:
        run(dbp)
    assert excinfo.value.code == 2
