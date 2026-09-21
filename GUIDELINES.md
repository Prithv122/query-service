# Safe Query Service — F2

**Tier:** 2 · **Category:** F - Querying & analysis · **Wave:** 2

Root rules in `../GUIDELINES.md` apply. This file is project-specific only — keep it under 40 lines.

## What this is

A parameterised, allowlisted query API over a DuckDB TPC-H warehouse: named SQL in the
catalog, four independent injection guards, a Parquet result cache, and one service object
behind both the CLI and the notebook.

## Stack

Python 3.13 · DuckDB (`tpch` extension) · pandas · PyArrow · pytest · ruff · GitHub Actions.
No accounts, no services, no env vars — hence no `.env.example`.

## Acceptance criteria

- [x] Safe parameterised query API over a warehouse (CATALOG F2)
- [x] Caching, CLI **and** notebook interface (`notebooks/demo.ipynb`)
- [x] SQL-injection awareness demonstrated, not asserted — adversarial test suite
- [ ] Ship gate passes

## Project-specific notes

- `uv run query-service build` needs network **once** to fetch the DuckDB `tpch` extension;
  after that it is offline. Tests build their own sf=0.01 warehouse in a tmp dir.
- The four guards live in `safety.py`; each has its own test. If a guard is relaxed, the
  README's §5 claims must be re-checked — they quote payload counts.
- Cache keys hash the **generated SQL**, not just parameters. Identifier substitution
  changes the SQL without changing a value; the earlier key served the wrong result.
- Local pytest needs `--basetemp=<scratchpad>/pt` (root `GUIDELINES.md` → Conventions).
