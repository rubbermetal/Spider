import json
import pytest
from spiderlib import cli, db

@pytest.fixture
def dbp(tmp_path):
    return str(tmp_path / "t.db")

def run(dbp, *args):
    return cli.main(["--db", dbp, *args])

def test_seed_add_and_list(dbp, capsys):
    assert run(dbp, "seed", "add", "http://a.com", "--max-depth", "2", "--max-pages", "50", "--no-external") == 0
    out, _ = capsys.readouterr()
    assert out.startswith("seed 1: http://a.com/")

    assert run(dbp, "seed", "list") == 0
    out, _ = capsys.readouterr()
    expected_output = "1\thttp://a.com/\ton\t2\t50\tno\t1\t0\n"
    assert out == expected_output

def test_seed_add_bad_url(dbp, capsys):
    assert run(dbp, "seed", "add", "mailto:x@y.z") == 2
    _, err = capsys.readouterr()
    assert "bad url" in err

def test_config_list_get_set(dbp, capsys):
    assert run(dbp, "config") == 0
    out, _ = capsys.readouterr()
    assert "respect_robots = true" in out

    assert run(dbp, "config", "respect_robots", "false") == 0
    out, _ = capsys.readouterr()
    assert out == "respect_robots = false\n"

    assert run(dbp, "config", "respect_robots") == 0
    out, _ = capsys.readouterr()
    assert out == "false\n"

    assert run(dbp, "config", "concurrency", "8") == 0
    capsys.readouterr()
    assert run(dbp, "config", "concurrency") == 0
    out, _ = capsys.readouterr()
    assert out == "8\n"

    conn = db.connect(dbp)
    settings = db.get_settings(conn)
    assert settings["concurrency"] == 8

def test_config_errors(dbp, capsys):
    assert run(dbp, "config", "nope") == 2
    _, err = capsys.readouterr()
    assert "unknown setting" in err

    assert run(dbp, "config", "concurrency", "abc") == 2
    _, err = capsys.readouterr()
    assert "bad value" in err

    assert run(dbp, "config", "respect_robots", "maybe") == 2

def test_status_empty(dbp, capsys):
    assert run(dbp, "status") == 0
    out, _ = capsys.readouterr()
    assert "state: stopped" in out
    assert "urls: 0 total, 0 domains" in out
    assert "errors last hour: 0" in out
    assert "robots.txt: respected" in out

def test_status_counts_and_robots_flag(dbp, capsys):
    assert run(dbp, "seed", "add", "http://a.com") == 0
    assert run(dbp, "config", "respect_robots", "false") == 0
    assert run(dbp, "status") == 0
    out, _ = capsys.readouterr()
    assert "  queued: 1" in out
    assert "robots.txt: IGNORED" in out

def test_pause_resume_stop(dbp, capsys):
    assert run(dbp, "pause") == 0
    out, _ = capsys.readouterr()
    assert "crawl_state: paused" in out

    assert run(dbp, "resume") == 0
    out, _ = capsys.readouterr()
    assert "crawl_state: running" in out

    assert run(dbp, "stop") == 0
    out, _ = capsys.readouterr()
    assert "crawl_state: stopped" in out

    conn = db.connect(dbp)
    audit_rows = conn.execute("SELECT * FROM audit").fetchall()
    assert len(audit_rows) == 3

def test_block_unblock(dbp, capsys):
    assert run(dbp, "block", "HTTP://Bad.com/x") == 0
    out, _ = capsys.readouterr()
    assert "blocked bad.com" in out

    conn = db.connect(dbp)
    domain_row = conn.execute("SELECT * FROM domains WHERE host = 'bad.com'").fetchone()
    assert domain_row["blocked"] == 1

    assert run(dbp, "unblock", "bad.com") == 0
    out, _ = capsys.readouterr()
    assert "unblocked bad.com" in out

    domain_row = conn.execute("SELECT * FROM domains WHERE host = 'bad.com'").fetchone()
    assert domain_row["blocked"] == 0

    assert run(dbp, "block", "evil.org") == 0
    out, _ = capsys.readouterr()
    assert "blocked evil.org" in out

def test_retry_errors(dbp, capsys):
    assert run(dbp, "seed", "add", "http://a.com") == 0
    conn = db.connect(dbp)
    conn.execute("UPDATE urls SET status='error', attempts=3, error='x'")
    conn.commit()

    assert run(dbp, "retry-errors") == 0
    out, _ = capsys.readouterr()
    assert "requeued 1" in out

    url_row = conn.execute("SELECT * FROM urls WHERE id = 1").fetchone()
    assert url_row["status"] == 'queued'
    assert url_row["attempts"] == 0
    assert url_row["error"] is None
