from __future__ import annotations

import datetime as dt

import pytest

from queryservice import catalog
from queryservice.safety import UnsafeQuery

HEADER = """/* {
  "description": "test",
  "params": {
    "since": {"type": "date"},
    "n":     {"type": "int", "required": false, "default": 5, "minimum": 1, "maximum": 10},
    "kind":  {"type": "enum", "values": ["a", "b"], "required": false, "default": "a"}
  },
  "identifiers": {"dim": ["x", "y"]}
} */
SELECT {dim} FROM t WHERE d >= $since AND n = $n AND k = $kind"""


@pytest.fixture
def query():
    return catalog.parse("demo", HEADER)


def test_every_shipped_query_parses_and_declares_its_parameters():
    queries = catalog.load_all()
    assert set(queries) == {
        "daily_order_volume",
        "late_shipments",
        "revenue_by_dimension",
        "top_customers",
    }
    for query in queries.values():
        assert query.description
        assert query.sql.lower().startswith("select")
        for param in query.params:
            assert f"${param.name}" in query.sql
        for identifier in query.identifiers:
            assert "{" + identifier + "}" in query.sql


def test_defaults_fill_in_and_dates_coerce(query):
    sql, values = query.bind({"since": "2024-01-01"})
    assert values == {"since": dt.date(2024, 1, 1), "n": 5, "kind": "a"}
    assert sql.startswith("SELECT x")  # first allowed identifier is the default


def test_identifier_substitution_is_allowlisted(query):
    sql, _ = query.bind({"since": "2024-01-01", "dim": "y"})
    assert sql.startswith("SELECT y")
    with pytest.raises(UnsafeQuery, match="dim must be one of"):
        query.bind({"since": "2024-01-01", "dim": "y; DROP TABLE t"})


def test_missing_required_parameter_is_refused(query):
    with pytest.raises(UnsafeQuery, match="requires parameter 'since'"):
        query.bind({})


def test_unknown_parameter_is_an_error_not_a_shrug(query):
    """Silently ignoring a misspelled filter is how someone reads an unfiltered number."""
    with pytest.raises(UnsafeQuery, match="Unknown parameters"):
        query.bind({"since": "2024-01-01", "sinse": "2024-01-01"})


@pytest.mark.parametrize(
    ("supplied", "match"),
    [
        ({"since": "not-a-date"}, "ISO date"),
        ({"since": "2024-01-01", "n": "twelve"}, "must be an integer"),
        ({"since": "2024-01-01", "n": 99}, "must be <= 10"),
        ({"since": "2024-01-01", "n": 0}, "must be >= 1"),
        ({"since": "2024-01-01", "kind": "c"}, "must be one of"),
        ({"since": "2024-01-01", "n": "5 OR 1=1"}, "must be an integer"),
    ],
)
def test_parameter_validation(query, supplied, match):
    with pytest.raises(UnsafeQuery, match=match):
        query.bind(supplied)


def test_a_header_is_required():
    with pytest.raises(ValueError, match="missing its JSON header"):
        catalog.parse("bare", "SELECT 1")


def test_an_identifier_with_no_allowed_values_is_refused():
    text = '/* {"identifiers": {"dim": []}} */\nSELECT {dim} FROM t'
    with pytest.raises(ValueError, match="hole, not a filter"):
        catalog.parse("holey", text)


def test_unknown_query_name_lists_what_exists():
    with pytest.raises(UnsafeQuery, match="No such query"):
        catalog.get("definitely_not_a_query")
