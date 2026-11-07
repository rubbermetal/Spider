import pytest
from spiderlib import cli, db
from datetime import datetime, timedelta

@pytest.fixture
def dbp(tmp_path):
    return str(tmp_path / "t.db")

def run(dbp, *args):
    return cli.main(["--db", dbp, *args])

def seed(dbp, url, hours, last=None, added="2026-01-01T00:00:00Z", enabled=1):
    conn = db.connect(dbp)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO seeds (url, enabled, recrawl_hours, last_crawled, added_at)
        VALUES (?, ?, ?, ?, ?)
    """, (url, enabled, hours, last, added))
    conn.commit()
    conn.close()

def test_schedule_empty(dbp, capsys):
    assert run(dbp, "schedule") == 0
    captured = capsys.readouterr()
    assert "no seeds have a recrawl interval" in captured.out

def test_schedule_lists_seeds(dbp, capsys):
    seed(dbp, "http://a.com/", 24, last="2026-11-06T10:00:00Z")
    seed(dbp, "http://b.com/", 6, added="2026-11-01T00:00:00Z")
    seed(dbp, "http://c.com/", 12, enabled=0)
    seed(dbp, "http://d.com/", None)  # Seed without interval
    assert run(dbp, "schedule") == 0
    captured = capsys.readouterr()
    lines = captured.out.strip().split('\n')
    assert len(lines) == 3
    assert lines[0].split('\t') == ["1", "http://a.com/", "24h", "2026-11-06T10:00:00Z", "2026-11-07T10:00:00Z"]
    assert lines[1].split('\t') == ["2", "http://b.com/", "6h", "-", "2026-11-01T06:00:00Z"]
    assert lines[2].split('\t') == ["3", "http://c.com/", "12h", "-", "disabled"]

def test_schedule_run_nothing_due(dbp, capsys):
    seed(dbp, "http://a.com/", 24, last=db.now())  # Fresh timestamp
    assert run(dbp, "schedule", "--run") == 0
    captured = capsys.readouterr()
    assert "nothing due" in captured.out

def test_schedule_run_requeues(dbp, capsys):
    seed(dbp, "http://a.com/", 1, last="2000-01-01T00:00:00Z")
    conn = db.connect(dbp)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO urls (url, host, seed_id, status, added_at)
        VALUES ('http://a.com/1', 'a.com', 1, 'done', ?)
    """, (db.now(),))
    conn.commit()
    conn.close()
    assert run(dbp, "schedule", "--run") == 0
    captured = capsys.readouterr()
    assert "seed 1: requeued 1" in captured.out
    conn = db.connect(dbp)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM urls WHERE url = 'http://a.com/1'")
    status = cursor.fetchone()[0]
    assert status == "queued"
    cursor.execute("SELECT actor, action FROM audit WHERE actor = 'scheduler'")
    audit = cursor.fetchone()
    assert tuple(audit) == ("scheduler", "seed_recrawl")
    conn.close()
