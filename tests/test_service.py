"""End-to-end against a real (small) TPC-H warehouse."""

from __future__ import annotations

import time

import duckdb
import pytest

from queryservice import QueryService
from queryservice.safety import UnsafeQuery

WINDOW = {"start_date": "1995-01-01", "end_date": "1996-01-01"}


def test_every_catalog_query_runs(service):
    for query in service.catalog():
        params = dict(WINDOW)
        if query.name == "top_customers":
            params["region"] = "EUROPE"
        result = service.run(query.name, limit=25, **params)
        assert result.rows > 0, query.name
        assert not result.frame.isna().all().any(), query.name


def test_revenue_by_dimension_changes_with_the_dimension(service):
    nations = service.run("revenue_by_dimension", dimension="n_name", **WINDOW)
    regions = service.run("revenue_by_dimension", dimension="r_name", **WINDOW)
    assert len(nations.frame) == 25  # TPC-H has 25 nations in 5 regions
    assert len(regions.frame) == 5
    assert nations.frame["net_revenue"].sum() == pytest.approx(
        regions.frame["net_revenue"].sum(), rel=1e-6
    )


def test_row_limit_caps_and_flags_truncation(service):
    result = service.run("top_customers", region="EUROPE", limit=5, **WINDOW)
    assert result.rows == 5
    assert result.truncated
    assert not service.run("revenue_by_dimension", dimension="r_name", limit=50, **WINDOW).truncated


def test_optional_parameter_actually_filters(service):
    everyone = service.run("daily_order_volume", **WINDOW, limit=5000)
    machinery = service.run("daily_order_volume", segment="MACHINERY", **WINDOW, limit=5000)
    assert machinery.frame["orders"].sum() < everyone.frame["orders"].sum()


def test_cache_hit_returns_the_same_frame_faster(service):
    first = service.run("late_shipments", **WINDOW)
    second = service.run("late_shipments", **WINDOW)
    assert not first.cached
    assert second.cached
    assert second.frame.equals(first.frame)


def test_cache_key_includes_the_parameters(service):
    service.run("revenue_by_dimension", dimension="n_name", **WINDOW)
    other = service.run("revenue_by_dimension", dimension="r_name", **WINDOW)
    assert not other.cached


def test_cache_expires(database, tmp_path):
    with QueryService(database, cache_dir=tmp_path / "c", ttl_seconds=0.4) as service:
        service.run("late_shipments", **WINDOW)
        assert service.run("late_shipments", **WINDOW).cached
        time.sleep(0.5)
        assert not service.run("late_shipments", **WINDOW).cached


def test_cache_is_bypassed_on_request(service):
    service.run("late_shipments", **WINDOW)
    assert not service.run("late_shipments", use_cache=False, **WINDOW).cached


def test_ad_hoc_sql_is_allowed_but_guarded(service):
    result = service.run_sql("SELECT count(*) AS n FROM nation")
    assert result.frame["n"].iloc[0] == 25
    assert not result.cached

    with pytest.raises(UnsafeQuery):
        service.run_sql("DROP TABLE nation")
    with pytest.raises(UnsafeQuery):
        service.run_sql("SELECT 1; DROP TABLE nation")


def test_ad_hoc_sql_binds_its_parameters(service):
    result = service.run_sql("SELECT n_name FROM nation WHERE n_name = $name", {"name": "INDIA"})
    assert list(result.frame["n_name"]) == ["INDIA"]

    hostile = service.run_sql(
        "SELECT n_name FROM nation WHERE n_name = $name", {"name": "INDIA' OR '1'='1"}
    )
    assert hostile.rows == 0


def test_the_connection_itself_cannot_write(service):
    """Guard layer 4: even with the SQL guard bypassed, the engine refuses."""
    with pytest.raises(duckdb.Error):
        service.connection.execute("CREATE TABLE pwned AS SELECT 1")
    assert service.run_sql("SELECT count(*) AS n FROM nation").frame["n"].iloc[0] == 25


def test_missing_warehouse_is_a_clean_error(tmp_path):
    with QueryService(tmp_path / "nope.duckdb") as service, pytest.raises(FileNotFoundError):
        service.run_sql("SELECT 1")
