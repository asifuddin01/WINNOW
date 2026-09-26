# Performance audit (Phase 9)

Guide section 2.2 sets the speed budgets and section 13 says how to check them. This
page records how they are measured, the latest results, and what the audit changed to
meet them.

## How it is measured

```bash
make perf                    # every budget; about 15 minutes
make perf parts=list         # or: imports, list, screening
make perf json=benchmarks/data/budgets.json
```

`backend/benchmarks/budgets.py` runs against the running stack, over HTTP, so middleware,
sessions and row-level security are all counted. It works in five steps:

1. **Account.** It makes a throwaway account (`e2e-perf-…@example.com`) and signs in,
   as the browser does.
2. **Imports and deduplication.** It imports 10,000 and then 100,000 RIS records, from
   upload to "done". Each import is measured only once the previous one's deduplication
   has finished. It then imports 50,000 records, a tenth of them second copies, and
   times the deduplication pass that follows.

   The records are real titles, abstracts and keywords from SYNERGY (CC0) when
   `benchmarks/synergy.py` has fetched them, and generated varied titles otherwise.
3. **Seeding.** It seeds 100,000 records exactly as `make seed-large` does.
4. **Records list.** It times the list under every filter, search and sort, a second
   page, and the filter counts beside it.
5. **Screening.** It screens about 40 records in relevance order and about 40 in random
   order, timing the queue and each decision.

   Every seeded record is given a score first, as just after a model has trained. On
   100,000 records a real first model takes longer than the run itself, so without this
   the relevance paths would only ever be timed with nothing scored.

**Whose time is measured.** Requests are paced under the API's limit of 600 a minute,
as a person's would be. Times are the API's own, from its `Server-Timing` header. What
the client saw on top of that is reported separately, together with the machine's load
average.

**The state of the database.** The `records` table is vacuumed before the run and
analysed after seeding: the state autovacuum keeps it in.

**Clean-up.** Everything the run made is deleted at the end (unless `--keep` is given,
for `EXPLAIN`), and the table is vacuumed again.

## Results

Measured on 2026-09-26 on the development stack: a Docker VM with 8 CPUs and 3.8 GB of
memory, on a Mac shared with other applications, at a load average of 2 to 5. The
guide's smallest server (2 vCPUs, 4 GB, SSD) has fewer cores but runs nothing else.

| Budget (guide 2.2) | Target | Measured |
| --- | --- | --- |
| Import 10,000 RIS records | < 10 s | **7.1 s** (worker 5.7 s) |
| Import 100,000 records | < 60 s | **48.7 s** |
| Deduplication, 50,000 records | < 30 s | **13.2 s** (5,000 duplicates merged) |
| Records list, 100,000 records, any filter (API p95) | < 150 ms | **12–64 ms** across 15 filters, sorts and searches; one search at **100–153 ms** across runs (see below) |
| Screening: next record (API p95), every record scored | < 80 ms | **32–36 ms**; **85 ms** while a 100,000-record retrain runs |
| Screening: saving a decision (API p95) | < 80 ms | **44–69 ms**; **87 ms** while a 100,000-record retrain runs |
| Initial JS bundle, gzipped | < 200 KB | **159.8 KB** |
| Initial page load (LCP, 4G) | < 1.5 s | **0.7 s** (sign-in page, production stack) |
| Lighthouse Performance / Accessibility | ≥ 95 / ≥ 95 | **95 / 100** on Lighthouse's default mobile profile; **100 / 100** on 4G and on desktop |
| Load test: 50 reviewers, one decision every 3 s each, 10 min (guide 13) | p95 < 100 ms, errors < 0.1% | **p95 37 ms**, **0 errors** in 19,920 requests |

What the client saw on top of the API: p50 3.6 ms, p95 9.3 ms.

### The two figures over their budget

- **`author:okafor year:2010..2024`, p95 153 ms (p50 92 ms).** `make seed-large` uses
  five authors, so any one of them is on 40% of the records. The planner expects a
  handful of matches and sorts them all. In a real review a surname is rare, and the
  trigram index finds its records directly.
- **Screening during a retrain, p95 85–87 ms.** At 100,000 records, the model's first
  retrain reads every record and scores them all, which takes minutes. Requests arriving
  meanwhile share the database with it. The worker already runs at a lower CPU weight
  (`cpu_shares: 256`). With no retrain running, the same requests stay under 40 ms.

## What the audit changed

| Found | Where | Change | Effect |
| --- | --- | --- | --- |
| Title and year sorts read and sorted the whole review for each page of 50 | records list | Ordered indexes `(project_id, title_norm, id DESC)` and `(project_id, year…, id DESC)`, both directions | 779 ms → 9 ms |
| Relevance order computed a score for every record, then sorted them all | records list | Two index reads: scored records best first, then unscored ones newest first | 700 ms → 3 ms |
| The "live records" index went unused: it said `= false`, the queries say `IS false` | records list | Rebuilt with the queries' predicate, and the id added | count 1.3 s → index-only; newest first 1 ms |
| A broad search counted 10,001 rows to say "10,000+" | records list | Count to 1,000 ("1,000+") | 2 s → under 0.2 s |
| Titles sharing their first words by the thousand made deduplication quadratic: it held the worker for over ten minutes | deduplication | Blocks capped at 200 records, split by more of the title | no block over 200 |
| Pair scoring blocked the worker's event loop, so other jobs waited | deduplication | Scoring runs in a thread | other jobs start meanwhile |
| Loading records for deduplication read every abstract for one yes or no | deduplication | The database answers the yes or no | 18 s → 4 s at 100,000 |
| Setting 5,000 clusters' kept records went through an `IN` list of 5,000 pairs | deduplication | Joined to a `VALUES` list | 22 s → under 1 s |
| Kept records were rewritten even when unchanged, and every rewrite touched every index | deduplication | Only changed rows are written | 26 s → 0 |
| The next-records query, in relevance order, joined and sorted every scored record | screening | The best scores are read straight off the index, 20 per record wanted, more only if the reviewer has decided those | 532 ms → 36 ms p95 |
| A settings change rewrote every record's status, changed or not | screening | Only changed statuses are written | decisions p95 163 → 87 ms during recompute |
| One COPY per 1,000 rows, one at a time | imports | 5,000 rows per COPY, two in flight, the next chunk parsed meanwhile | 100,000 records 93 s → 49 s |
| `VACUUM` failed: Docker's default 64 MB of `/dev/shm` | database | `shm_size: 256mb` | |
| Stock PostgreSQL settings | database | SSD costs, room for bulk loads between checkpoints | |
| The worker's health check imported all of Winnow, taking longer than its own timeout | worker | Reads the worker's heartbeat from Redis | healthy |
| The "Included · Undo" toast sat over the decision buttons, catching the next click | screening page | Shown at the top | |

The audit also found that the admin health page counted only the admin's own records
(fixed in Phase 9 item 4's follow-up).

## Known limits

- **A retrain that runs past its 10-minute timeout keeps a core busy until it ends.** A
  Python thread cannot be stopped. It was seen only on `seed-large`'s near-identical
  texts. Running training in a separate process would make it stoppable, at the cost of
  the corpus cache (`app/workers/ranking.py`).
- **Every import pays for three GIN indexes and a stemmed search vector per record,**
  about 0.5 ms a row here. A faster disk or more cores bring it down; there is little
  left to trim in Winnow itself.

## Page load and Lighthouse (production stack)

Measured with Lighthouse 12 against the production stack (`docker-compose.prod.yml`) on
this machine, on the sign-in page, which is every visitor's first page:

| Profile | Performance | Accessibility | LCP | First paint |
| --- | --- | --- | --- | --- |
| Lighthouse's default mobile (1.6 Mbps, 150 ms round trips, 4× slower CPU) | 95 | 100 | 2.5 s | 2.3 s |
| 4G (9 Mbps, 60 ms, 4× slower CPU) | 100 | 100 | 0.7 s | 0.7 s |
| Desktop | 100 | 100 | 0.5 s | 0.5 s |

The default mobile profile is what Chrome calls "Fast 3G", despite Lighthouse's "slow 4G"
label, and the page stays short of 1.5 s there. There the page waits on round trips, not
bytes: the HTML, then the app's code, then the sign-in page's own code.

Two changes helped:

- **Tooltips belong to the signed-in shell.** The first-load JavaScript went from
  178 KB to 160 KB.
- **The sign-in page no longer waits for its two API calls before loading its code.**
  The score went from 94 to 95.

## Load test (guide 13)

`make load` (see `load/README.md`) runs the test on one review of 20,000 records. Each of
50 reviewers asks for the next records and decides one, every 3 seconds on average,
independently, for 10 minutes. The acceptance run used the production stack: four API
workers, as on the guide's smallest server, with TLS through Caddy.

| Measure | Result |
| --- | --- |
| Requests | 19,920, at 33 a second |
| Median | 12.7 ms |
| p90 | 22 ms |
| p95 | **37 ms** (budget 100) |
| Errors | **0** (budget 0.1%) |

k6 dropped 41 of the 10,000 planned iterations, when all 50 of its virtual reviewers were
waiting on the slowest few requests (up to 5 s).

The runs before that found four defects, all fixed:

- **Conflict notices failed under sustained use.** The upsert that counts a reviewer's
  new conflicts named its partial index with a bound parameter. PostgreSQL plans a
  prepared statement for its actual values five times, then generically, and the
  generic plan could not use the index. From then on, every decision that made a
  conflict was a 500. `test_notifications.py` now runs it eight times on one connection.
- **The best-scored records were sorted in full** (see the screening row above).
- **A Redis connection slow to open became a 500.** The client now retries.
- **GIN indexes merged their pending lists inside requests.** Status updates took up to
  1.8 s, whoever filled a list paying for it. Bigger lists and earlier autovacuum on
  `records` moved the merging to the background: p95 went from 120 ms to 55 ms, and
  37 ms over the full run.

A database pool that closed its spare connections as soon as they were returned was also
fixed; it now keeps ten per process.

The first runs made all 50 reviewers click in the same instant, forever, because of k6's
looping virtual users with `sleep(3)`. That gave p95 of 450–700 ms, a measure of a wave
of 50 simultaneous requests rather than of 50 people screening.

On the development stack, a single Uvicorn process with `--reload`, requests arriving
together queue behind each other. Measure load on the production stack.
