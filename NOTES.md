# Build Notes — Safe Query Service

---

## Log

### 2026-08-30 — build

- **Two real bugs, both caught by tests, both worth keeping in the write-up.**

  1. `PRAGMA database_list` sailed through `assert_read_only`. DuckDB reports it as a
     `SELECT` statement — it rewrites the pragma into a select plan. The parser guard was
     doing exactly what I asked and my assumption about what "SELECT" meant was wrong.
     Fix: a first-keyword check *on top of* the parser (not instead of it), with leading
     comments and whitespace stripped first so `-- hi\nSELECT 1` still passes.
  2. The cache key was `name + bound values + limit + warehouse fingerprint`, which misses
     the allowlisted **identifier** — the group-by dimension changes the SQL without
     changing a single bound value. `revenue_by_dimension(dimension=r_name)` was served the
     cached `n_name` result: 25 rows where 5 were expected. Fix: hash the generated SQL.
     This is the failure mode I care most about, because nothing errors — you just read a
     wrong number that looks plausible.

- **Why the parser instead of a blocklist.** My first sketch had a regex looking for `;`,
  `--`, `DROP`, `DELETE`. Every version of that I wrote, I could think of a way around
  within a minute (`/**/`, string literals containing a semicolon, `dRoP`). Asking DuckDB
  "how many statements is this and what type is the first one" has no such gap, because it
  is the same parser that will execute the thing.

- **Read-only connection as the last line.** `duckdb.connect(path, read_only=True)` means a
  hypothetical bypass of the three guards above still cannot write. It also lets the CLI,
  a notebook and the test suite hold the same file open at once, which a read-write
  connection would not.

- **TPC-H over another synthetic generator.** Project 13 already ships a bespoke generator
  and it took real effort; here the point is the *service*, not the data, and DuckDB's
  `tpch` extension gives a schema an interviewer recognises for one line of code. Tests
  generate sf=0.01 (~60k line items, about a second); the README numbers are sf=0.1.

- **Cache honesty.** The speedup is 8.6–22.1× on the join-heavy queries and only 2.2× on
  `daily_order_volume`, which is already ~7 ms cold. Reading Parquet back has a ~3 ms floor.
  Reported both rather than quoting the flattering average.

---

## Rejected approaches

| Approach | Why rejected |
|---|---|
| Keyword/regex blocklist for injection | Loses to comments, string literals and case tricks. Delegated to `duckdb.extract_statements` instead |
| Escaping user-supplied identifiers | Requires being right about every quoting rule in the engine. An allowlist requires being right about a list |
| Caching ad-hoc SQL results | Unbounded key space, single-use entries, and the ad-hoc path is the one most likely to be exploratory anyway |
| `LIMIT $n` inside catalog SQL | The row cap is a guard concern, not a query concern — it belongs in the wrapper that every path shares, including ad-hoc SQL |
| Python constants for the SQL | The `.sql` files diff and review as SQL, and the JSON header keeps the parameter contract next to the query |
| An HTTP API | C2 (`fastapi-service`) is the deployed-API project. Adding a web layer here would duplicate it and bury the actual subject, which is the guard and cache design |

## Open questions

- [ ] Query timeout and a scanned-bytes budget — the row cap limits what comes back, not what gets scanned. That is the real DoS surface.
- [ ] `EXPLAIN ANALYZE` capture behind a `--profile` flag, so the CLI can show which query is worth caching rather than my guessing from the timings.
- [ ] Cache stampede: two processes asking the same cold question both scan. Single-flight would fix it, and matters the moment this is shared.
