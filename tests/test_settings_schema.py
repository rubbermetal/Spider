import pytest
from spiderlib import db
from spiderlib.admin import settings_schema as ss

@pytest.fixture
def conn(tmp_path):
    return db.connect(str(tmp_path / "t.db"))

def field(key):
    return next(f for f in ss.FIELDS if f["key"] == key)

def get_audit(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id")]

def test_fields_cover_editable_settings():
    assert {f["key"] for f in ss.FIELDS} == set(db.DEFAULT_SETTINGS) - {"crawl_state"}
    for f in ss.FIELDS:
        assert set(f.keys()) == {"key", "label", "group", "kind", "min", "max", "help"}

def test_groups_order():
    titles = [title for title, _ in ss.groups()]
    assert titles == ["Politeness", "Limits", "Retries"]
    assert len([f for f in ss.FIELDS if f["group"] == "Politeness"]) == 4

def test_validate_int():
    assert ss.validate(field("concurrency"), " 8 ") == (8, None)
    assert ss.validate(field("concurrency"), "abc")[1] == "must be a whole number"
    assert ss.validate(field("concurrency"), "0")[0] is None and "between 1 and 32" in ss.validate(field("concurrency"), "0")[1]
    assert "between 1 and 32" in ss.validate(field("concurrency"), "33")[1]
    assert ss.validate(field("concurrency"), "2.5")[1] == "must be a whole number"

def test_validate_float():
    assert ss.validate(field("default_delay"), "0.5") == (0.5, None)
    assert "must be a number" in ss.validate(field("default_delay"), "x")[1]
    assert "must be a number" in ss.validate(field("default_delay"), "nan")[1]
    assert "must be a number" in ss.validate(field("default_delay"), "inf")[1]
    assert "between" in ss.validate(field("default_delay"), "-1")[1]

def test_validate_str():
    assert ss.validate(field("user_agent"), "  Bot/1 (+http://x.org)  ") == ("Bot/1 (+http://x.org)", None)
    assert "1-200 characters" in ss.validate(field("user_agent"), "")[1]
    assert "1-200 characters" in ss.validate(field("user_agent"), "a" * 201)[1]
    assert "contains control characters" in ss.validate(field("user_agent"), "bad\x01agent")[1]

def test_apply_changes_saves_and_audits(conn):
    form = {"concurrency": "6", "default_delay": "0.5"}
    changes, errors = ss.apply_changes(conn, form)
    assert errors == {}
    settings = db.get_settings(conn)
    assert settings["concurrency"] == 6
    assert settings["default_delay"] == 0.5
    assert settings["respect_robots"] is False
    assert settings["allow_external"] is False
    assert sorted(changes) == sorted([("concurrency", 4, 6), ("respect_robots", True, False), ("default_delay", 2.0, 0.5)])
    audit = get_audit(conn)
    assert len(audit) == 3
    for entry in audit:
        assert entry["actor"] == "admin"
        assert entry["action"] == "set_setting"
    assert any(entry["detail"] == "concurrency: 4 -> 6" for entry in audit)

def test_apply_changes_nothing_changed(conn):
    form = {"respect_robots": "1"}
    changes, errors = ss.apply_changes(conn, form)
    assert changes == []
    assert errors == {}
    audit = get_audit(conn)
    assert len(audit) == 0

def test_apply_changes_is_atomic_on_error(conn):
    form = {"concurrency": "6", "default_delay": "abc", "respect_robots": "1"}
    changes, errors = ss.apply_changes(conn, form)
    assert changes == []
    assert "default_delay" in errors and "must be a number" in errors["default_delay"]
    settings = db.get_settings(conn)
    assert settings["concurrency"] == 4
    audit = get_audit(conn)
    assert len(audit) == 0

def test_checkbox_semantics(conn):
    form = {"respect_robots": "1", "allow_external": "1"}
    changes, errors = ss.apply_changes(conn, form)
    assert errors == {}
    settings = db.get_settings(conn)
    assert settings["allow_external"] is True
    assert settings["respect_robots"] is True
    assert changes == [("allow_external", False, True)]
    audit = get_audit(conn)
    assert len(audit) == 1
    assert audit[0]["detail"] == "allow_external: False -> True"
