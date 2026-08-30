# Interview Prep — Safe Query Service

---

### Q1. Walk me through the architecture in 90 seconds.

_A:_ A catalog of named SQL files, each with a JSON header declaring its typed parameters
and any allowlisted identifiers. `QueryService` is the single entry point: it looks up the
query, coerces and validates parameters, formats in only allowlisted identifiers, proves
the SQL is one read statement, wraps it in a row cap, checks a Parquet cache keyed on the
generated SQL plus values plus warehouse fingerprint, and executes on a read-only DuckDB
connection. The CLI and the notebook are thin skins over that same object, so there is one
code path to secure and one to test. The warehouse is TPC-H, generated locally by DuckDB.

### Q2. Why not just sanitise the input with a regex or reject queries containing `DROP`?

_A:_ Because I can beat that in a minute and so can an attacker: block comments, string
literals containing a semicolon, mixed case, `PRAGMA` instead of `DROP`. A blocklist has to
enumerate every bad thing, forever, including statement types DuckDB adds next year. So I
ask the engine's own parser instead — `duckdb.extract_statements` tells me how many
statements the text is and what type the first one is, and I require exactly one read.
The one place text genuinely must reach SQL is a dynamic column name, because identifiers
cannot be bound as parameters; that is an allowlist declared in the query file and checked
by set membership, not by pattern.

### Q3. What's the weakest part of this, and what would break first under load?

_A:_ The row cap protects the result set, not the scan — a legal query over the whole fact
table is expensive no matter how few rows come back. Under load that is the failure, not
injection: no timeout, no scanned-bytes budget, no per-user concurrency limit. Second is
the cache: it is a local directory, so N analysts get N copies and a cold key causes N
simultaneous scans (no single-flight). Both are in the README's 100× section — Redis or
object storage for the cache, and pushing the read-only guarantee down into a database
role with `SELECT`-only grants rather than a Python keyword argument.

### Q4. How do you know it works? What did you measure, and against what baseline?

_A:_ 59 tests, of which the adversarial suite fires 13 payloads that would succeed against
a string-concatenating service, plus five hostile identifiers, and asserts each is rejected
by a *named* guard before touching the database — and separately that the connection itself
refuses a `CREATE TABLE` even if you hand it straight to DuckDB. For the cache I measured
median-of-5 cold and warm timings per query: 18.7×, 22.1× and 8.6× on the join-heavy
queries, and only 2.2× on the cheap one, because reading Parquet back has a ~3 ms floor. I
report that last number because the average would flatter the design.

### Q5. Your test suite passed, and then you found two bugs anyway. What were they, and what did they change about how you build this kind of thing?

_A:_ First, `PRAGMA database_list` was accepted: DuckDB rewrites it into a SELECT plan, so
my "is it a SELECT" guard said yes. I added a first-keyword check on top of the parser —
the lesson being that delegating to the parser is right, but you must know exactly what
question you asked it. Second, and worse, the cache key omitted the allowlisted identifier,
so asking for revenue by region returned the cached by-nation result: 25 rows presented as
5 regions, no error anywhere. That one changed my default — cache keys now hash the
*generated SQL*, not the inputs I think determine it, because a wrong-but-plausible number
is more dangerous than a crash and there is nothing to alert on.

---

## 30-second pitch

A query API over a DuckDB TPC-H warehouse that lets analysts run parameterised business
questions from a CLI or a notebook without an engineer in the loop, and without the usual
string-concatenation hole. Four independent guards — bound values, allowlisted identifiers,
parser-verified single read statement, read-only connection with a row cap — verified by an
adversarial suite of 13 payloads. Results are cached in Parquet with a key that includes the
warehouse fingerprint and the generated SQL, which gives 8.6–22.1× on the join-heavy
queries and, more importantly, cannot serve one question's answer to another.
