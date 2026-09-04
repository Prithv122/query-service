from __future__ import annotations

import json

import pytest

from queryservice import __version__, cli

WINDOW = ["--param", "start_date=1995-01-01", "--param", "end_date=1996-01-01"]


@pytest.fixture
def base(database, tmp_path):
    return ["--database", str(database), "--cache-dir", str(tmp_path / "cache")]


def test_version_is_set():
    assert __version__


def test_list_and_describe(base, capsys):
    assert cli.main([*base, "list", "-v"]) == 0
    out = capsys.readouterr().out
    assert "revenue_by_dimension" in out
    assert "allowlisted" in out

    assert cli.main([*base, "describe", "top_customers"]) == 0
    out = capsys.readouterr().out
    assert "--- SQL ---" in out
    assert "$region" in out


def test_run_as_json(base, capsys):
    code = cli.main([*base, "run", "late_shipments", *WINDOW, "--format", "json"])
    assert code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert {"priority", "late_share"} <= set(payload[0])
    assert "from warehouse in" in captured.err


def test_second_run_is_served_from_cache(base, capsys):
    cli.main([*base, "run", "late_shipments", *WINDOW])
    capsys.readouterr()
    cli.main([*base, "run", "late_shipments", *WINDOW])
    assert "from cache in" in capsys.readouterr().err


def test_no_cache_flag(base, capsys):
    cli.main([*base, "run", "late_shipments", *WINDOW])
    capsys.readouterr()
    cli.main([*base, "run", "late_shipments", *WINDOW, "--no-cache"])
    assert "from warehouse in" in capsys.readouterr().err


def test_cache_stats_and_clear(base, capsys):
    cli.main([*base, "run", "late_shipments", *WINDOW])
    capsys.readouterr()
    cli.main([*base, "cache"])
    assert json.loads(capsys.readouterr().out)["entries"] == 1
    cli.main([*base, "cache", "--clear"])
    assert "Removed 1" in capsys.readouterr().out


def test_cache_command_uses_default_dir_when_unset(database, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["--database", str(database), "cache"]) == 0
    assert json.loads(capsys.readouterr().out)["entries"] == 0


def test_hostile_identifier_is_rejected_with_exit_2(base, capsys):
    code = cli.main(
        [*base, "run", "revenue_by_dimension", *WINDOW, "--param", "dimension=n_name; DROP TABLE t"]
    )
    assert code == 2
    assert "Rejected: dimension must be one of" in capsys.readouterr().err


def test_malformed_param_is_rejected(base, capsys):
    assert cli.main([*base, "run", "late_shipments", "--param", "start_date"]) == 2
    assert "name=value" in capsys.readouterr().err


def test_ad_hoc_sql_command(base, capsys):
    assert cli.main([*base, "sql", "SELECT count(*) AS n FROM region", "--format", "csv"]) == 0
    assert "5" in capsys.readouterr().out


def test_ad_hoc_write_is_rejected(base, capsys):
    assert cli.main([*base, "sql", "DROP TABLE region"]) == 2
    assert "Rejected:" in capsys.readouterr().err
