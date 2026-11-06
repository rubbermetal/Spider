import pytest
from spiderlib.admin.seeds_form import parse_limits

def test_all_blank():
    assert parse_limits({}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {})
    assert parse_limits({"max_depth": "", "max_pages": " ", "recrawl_hours": "", "allow_external": ""}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {})

def test_valid_values():
    assert parse_limits({"max_depth": " 3 ", "max_pages": "500", "recrawl_hours": "24", "allow_external": "yes"}) == ({"max_depth": 3, "max_pages": 500, "recrawl_hours": 24, "allow_external": True}, {})
    assert parse_limits({"max_depth": " 3 ", "max_pages": "500", "recrawl_hours": "24", "allow_external": "no"}) == ({"max_depth": 3, "max_pages": 500, "recrawl_hours": 24, "allow_external": False}, {})

def test_boundaries():
    assert parse_limits({"max_depth": "0"}) == ({"max_depth": 0, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {})
    assert parse_limits({"max_depth": "50"}) == ({"max_depth": 50, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {})
    assert parse_limits({"max_depth": "51"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_depth": "must be a whole number between 0 and 50"})
    assert parse_limits({"max_depth": "-1"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_depth": "must be a whole number between 0 and 50"})
    assert parse_limits({"max_pages": "1"}) == ({"max_depth": None, "max_pages": 1, "recrawl_hours": None, "allow_external": None}, {})
    assert parse_limits({"max_pages": "0"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_pages": "must be a whole number between 1 and 10000000"})
    assert parse_limits({"recrawl_hours": "87600"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": 87600, "allow_external": None}, {})
    assert parse_limits({"recrawl_hours": "87601"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"recrawl_hours": "must be a whole number between 1 and 87600"})
    assert parse_limits({"recrawl_hours": "0"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"recrawl_hours": "must be a whole number between 1 and 87600"})

def test_not_numbers():
    assert parse_limits({"max_depth": "abc"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_depth": "must be a whole number between 0 and 50"})
    assert parse_limits({"max_depth": "2.5"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_depth": "must be a whole number between 0 and 50"})
    assert parse_limits({"max_pages": "abc"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_pages": "must be a whole number between 1 and 10000000"})
    assert parse_limits({"max_pages": "2.5"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"max_pages": "must be a whole number between 1 and 10000000"})
    assert parse_limits({"recrawl_hours": "abc"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"recrawl_hours": "must be a whole number between 1 and 87600"})
    assert parse_limits({"recrawl_hours": "2.5"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"recrawl_hours": "must be a whole number between 1 and 87600"})

def test_bad_external():
    assert parse_limits({"allow_external": "maybe"}) == ({"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}, {"allow_external": "choose default, yes or no"})

def test_multiple_errors():
    result = parse_limits({"max_depth": "x", "max_pages": "y"})
    assert result[0] == {"max_depth": None, "max_pages": None, "recrawl_hours": None, "allow_external": None}
    assert result[1].keys() == {"max_depth", "max_pages"}
