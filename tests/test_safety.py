"""The adversarial suite.

Each test is a payload that works against a service built by string-concatenating user
input into SQL. The point is not that DuckDB happens to reject them -- it is that they are
rejected *before* reaching DuckDB, by a named guard, with a message that says which one.
"""

from __future__ import annotations

import pytest

from queryservice import safety
from queryservice.safety import UnsafeQuery

STACKED = [
    "SELECT 1; DROP TABLE customer",
    "SELECT 1; DELETE FROM orders",
    "SELECT 1;SELECT 2",
    "SELECT 1; ATTACH 'evil.db' AS evil",
]

NOT_READS = [
    "DROP TABLE customer",
    "DELETE FROM orders WHERE 1=1",
    "UPDATE customer SET c_name = 'x'",
    "INSERT INTO nation VALUES (99, 'X', 0, '')",
    "CREATE TABLE pwned AS SELECT 1",
    "COPY customer TO 'stolen.csv'",
    "INSTALL httpfs",
    "PRAGMA database_list",
    "ATTACH 'other.db' AS other",
]


@pytest.mark.parametrize("sql", STACKED)
def test_stacked_statements_are_rejected(sql):
    with pytest.raises(UnsafeQuery, match="exactly one statement"):
        safety.assert_read_only(sql)


@pytest.mark.parametrize("sql", NOT_READS)
def test_only_read_statements_are_allowed(sql):
    with pytest.raises(UnsafeQuery, match="read statements"):
        safety.assert_read_only(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "WITH x AS (SELECT 1 AS n) SELECT n FROM x",
        "SELECT * FROM customer WHERE c_name = $name",
        "SELECT 1 -- a trailing comment",
        "SELECT 1; -- a trailing semicolon and comment",
    ],
)
def test_plain_reads_pass(sql):
    safety.assert_read_only(sql)


def test_unparseable_sql_is_rejected_not_crashed():
    with pytest.raises(UnsafeQuery, match="Could not parse"):
        safety.assert_read_only("SELECT FROM WHERE )(")


def test_identifier_allowlist_is_membership_not_pattern_matching():
    assert safety.validate_identifier("n_name", ["n_name", "r_name"]) == "n_name"
    for hostile in [
        "n_name; DROP TABLE customer",
        "n_name)) UNION ALL SELECT c_phone FROM customer --",
        '"n_name"',
        "N_NAME",
        "n_name ",
    ]:
        with pytest.raises(UnsafeQuery, match="must be one of"):
            safety.validate_identifier(hostile, ["n_name", "r_name"], label="dimension")


def test_limit_is_clamped_not_trusted():
    assert safety.clamp_limit(None) == safety.DEFAULT_ROW_LIMIT
    assert safety.clamp_limit(10) == 10
    assert safety.clamp_limit(10**9) == safety.MAX_ROW_LIMIT
    with pytest.raises(UnsafeQuery):
        safety.clamp_limit(0)


def test_wrap_preserves_inner_query_semantics():
    wrapped = safety.wrap_with_limit("SELECT n FROM t ORDER BY n DESC LIMIT 5", 3)
    assert wrapped.count("LIMIT") == 2
    assert "ORDER BY n DESC LIMIT 5" in wrapped
    assert wrapped.rstrip().endswith("LIMIT 3")


def test_wrap_strips_a_trailing_semicolon():
    """Without this the wrapper becomes two statements and the guard rejects its own SQL."""
    wrapped = safety.wrap_with_limit("SELECT 1;", 5)
    safety.assert_read_only(wrapped)
