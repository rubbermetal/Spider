import pytest
from spiderlib.admin import logs_filter as lf

def test_log_defaults():
    assert lf.parse_log_args({}) == {"q": "", "level": "", "page": 1, "per_page": 50}

def test_log_valid():
    assert lf.parse_log_args({"q": " boom ", "level": "error", "page": "3", "per_page": "200"}) == {"q": "boom", "level": "error", "page": 3, "per_page": 200}

def test_log_invalid_values():
    assert lf.parse_log_args({"level": "fatal", "page": "0", "per_page": "7"}) == {"q": "", "level": "", "page": 1, "per_page": 50}
    assert lf.parse_log_args({"page": "x"}) == {"q": "", "level": "", "page": 1, "per_page": 50}
    assert lf.parse_log_args({"page": "-2"}) == {"q": "", "level": "", "page": 1, "per_page": 50}
    assert lf.parse_log_args({"per_page": "26"}) == {"q": "", "level": "", "page": 1, "per_page": 50}
    assert lf.parse_log_args({"q": "a" * 500}) == {"q": "a" * 200, "level": "", "page": 1, "per_page": 50}

def test_audit_defaults_and_valid():
    assert lf.parse_audit_args({}) == {"q": "", "actor": "", "action": "", "page": 1, "per_page": 50}
    assert lf.parse_audit_args({"q": "x", "actor": " admin ", "action": "seed_add", "page": "2", "per_page": "25"}) == {"q": "x", "actor": "admin", "action": "seed_add", "page": 2, "per_page": 25}
    assert lf.parse_audit_args({"actor": "a" * 80}) == {"q": "", "actor": "a" * 50, "action": "", "page": 1, "per_page": 50}
    assert lf.parse_audit_args({"action": "a" * 90}) == {"q": "", "actor": "", "action": "a" * 60, "page": 1, "per_page": 50}

def test_query_dict():
    assert lf.query_dict(lf.parse_log_args({})) == {}
    assert lf.query_dict(lf.parse_log_args({"q": "x", "level": "warn", "per_page": "100", "page": "4"})) == {"q": "x", "level": "warn", "per_page": 100}
    assert lf.query_dict(lf.parse_audit_args({"actor": "admin", "action": "stop", "page": "9"})) == {"actor": "admin", "action": "stop"}
