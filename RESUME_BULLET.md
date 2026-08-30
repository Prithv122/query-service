# Resume Bullets — Safe Query Service

---

## Bullets

- Built a parameterised query service over a 600k-row DuckDB TPC-H warehouse with four
  independent injection guards (bound values, per-query identifier allowlists,
  parser-verified single-read statements via `duckdb.extract_statements`, and a read-only
  connection with row caps), verified by a 59-test suite whose adversarial half fires 13
  payloads — stacked statements, `PRAGMA`, `COPY`/`ATTACH`, comment-terminated injections
  — that defeat a string-concatenating implementation.
- Added a Parquet result cache keyed on the generated SQL, bound values, row limit and
  warehouse fingerprint, cutting repeat query latency 8.6–22.1× on join-heavy queries;
  the key design was driven by a test that caught the naive name+parameters key serving a
  by-nation result to a by-region request.

## Which roles this supports

- [ ] Data Scientist / ML
- [ ] AI Engineer (LLM/NLP/CV)
- [x] Data Engineer
- [x] Data Analyst / Python Developer

## Keywords this project earns

DuckDB · TPC-H · SQL injection defence in depth · prepared statements / parameter binding ·
identifier allowlisting · parser-based statement validation · read-only connections ·
result caching and invalidation · cache key design · Parquet · CLI tooling (argparse) ·
notebook API design · pytest (adversarial/parametrised) · ruff · GitHub Actions

---

_Note to self: the strongest thing to say out loud is the cache-key bug. Anyone can list
guards; explaining why a wrong-but-plausible cached number is scarier than an exception is
the part that sounds like experience._
