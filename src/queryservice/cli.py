"""Console entry point: build, list, describe, run, sql, cache."""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import warehouse
from .cache import ResultCache
from .catalog import Query
from .client import QueryService
from .safety import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT, UnsafeQuery


def _stdout_utf8() -> None:
    """Windows consoles still default to a legacy code page that cannot encode U+2192."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _parse_params(pairs: list[str] | None) -> dict[str, str]:
    params: dict[str, str] = {}
    for pair in pairs or []:
        name, sep, value = pair.partition("=")
        if not sep:
            raise UnsafeQuery(f"--param expects name=value, got {pair!r}")
        params[name.strip()] = value
    return params


def _emit(frame: pd.DataFrame, fmt: str) -> None:
    if fmt == "csv":
        print(frame.to_csv(index=False).rstrip())
    elif fmt == "json":
        print(frame.to_json(orient="records", date_format="iso", indent=2))
    else:
        with pd.option_context("display.width", 180, "display.max_columns", 30):
            print(frame.to_string(index=False, na_rep="-"))


def _describe(query: Query) -> str:
    lines = [f"{query.name}", f"    {query.description}"]
    if query.params:
        lines.append("    parameters:")
        for param in query.params:
            bits = [param.type]
            if not param.required:
                bits.append(f"optional, default {param.default!r}")
            if param.values:
                bits.append(f"one of {list(param.values)}")
            if param.minimum is not None or param.maximum is not None:
                bits.append(f"range {param.minimum}..{param.maximum}")
            lines.append(f"      {param.name:<12} {'; '.join(bits)}")
            if param.description:
                lines.append(f"          {param.description}")
    for name, allowed in query.identifiers.items():
        lines.append(f"    identifier {name}: one of {list(allowed)} (allowlisted)")
    return "\n".join(lines)


def cmd_build(args: argparse.Namespace) -> int:
    counts = warehouse.build(args.database, scale_factor=args.scale_factor)
    print(f"Built {args.database} at scale factor {args.scale_factor}")
    for table, count in counts.items():
        print(f"  {table:<10} {count:>9,} rows")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with QueryService(args.database) as service:
        for query in service.catalog():
            print(_describe(query) if args.verbose else f"{query.name}\n    {query.description}")
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    with QueryService(args.database) as service:
        print(_describe(service.describe(args.name)))
        print("\n--- SQL ---")
        print(service.describe(args.name).sql)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    with QueryService(
        args.database, cache_dir=args.cache_dir, ttl_seconds=args.ttl, use_cache=not args.no_cache
    ) as service:
        result = service.run(args.name, limit=args.limit, **_parse_params(args.param))
    _emit(result.frame, args.format)
    source = "cache" if result.cached else "warehouse"
    note = "  [truncated by row limit]" if result.truncated else ""
    print(
        f"\n{result.rows:,} rows from {source} in {result.elapsed_ms:.1f} ms{note}", file=sys.stderr
    )
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    with QueryService(args.database) as service:
        result = service.run_sql(args.sql, limit=args.limit)
    _emit(result.frame, args.format)
    print(f"\n{result.rows:,} rows in {result.elapsed_ms:.1f} ms", file=sys.stderr)
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    cache = ResultCache(directory=args.cache_dir, ttl_seconds=args.ttl)
    if args.clear:
        print(f"Removed {cache.clear()} cached results")
    else:
        print(json.dumps(cache.stats(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="query-service", description=__doc__)
    parser.add_argument("--database", default=str(warehouse.DEFAULT_DB))
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--ttl", type=float, default=900.0, help="Cache TTL in seconds")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_output(p: argparse.ArgumentParser) -> None:
        p.add_argument("--format", choices=("table", "csv", "json"), default="table")
        p.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_ROW_LIMIT,
            help=f"Row cap (hard maximum {MAX_ROW_LIMIT:,})",
        )

    p_build = sub.add_parser("build", help="Generate the TPC-H warehouse")
    p_build.add_argument("--scale-factor", type=float, default=0.1)
    p_build.set_defaults(func=cmd_build)

    p_list = sub.add_parser("list", help="List catalog queries")
    p_list.add_argument("-v", "--verbose", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_desc = sub.add_parser("describe", help="Show one query, its parameters and its SQL")
    p_desc.add_argument("name")
    p_desc.set_defaults(func=cmd_describe)

    p_run = sub.add_parser("run", help="Run a catalog query")
    p_run.add_argument("name")
    p_run.add_argument("--param", action="append", metavar="NAME=VALUE")
    p_run.add_argument("--no-cache", action="store_true")
    add_output(p_run)
    p_run.set_defaults(func=cmd_run)

    p_sql = sub.add_parser("sql", help="Run ad-hoc read-only SQL through the same guards")
    p_sql.add_argument("sql")
    add_output(p_sql)
    p_sql.set_defaults(func=cmd_sql)

    p_cache = sub.add_parser("cache", help="Cache statistics, or --clear")
    p_cache.add_argument("--clear", action="store_true")
    p_cache.set_defaults(func=cmd_cache)

    return parser


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UnsafeQuery as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
