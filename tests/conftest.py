from __future__ import annotations

import pytest

from queryservice import QueryService, warehouse

#: Scale factor 0.01 is ~60k line items -- big enough for the joins to be real, small
#: enough to generate in about a second at the start of the session.
TEST_SCALE_FACTOR = 0.01


@pytest.fixture(scope="session")
def database(tmp_path_factory):
    path = tmp_path_factory.mktemp("warehouse") / "tpch.duckdb"
    warehouse.build(path, scale_factor=TEST_SCALE_FACTOR)
    return path


@pytest.fixture
def service(database, tmp_path):
    with QueryService(database, cache_dir=tmp_path / "cache") as client:
        yield client
