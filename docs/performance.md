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
| Records list, 100,000 records, any filter (API p95) | < 150 ms | **12–45 ms** across 15 filters, sorts and searches; one search at **153 ms** (see below) |
| Screening: next record (API p95) | < 80 ms | **24–30 ms**; **44–85 ms** while a 100,000-record retrain runs |
| Screening: saving a decision (API p95) | < 80 ms | **33–39 ms**; **87 ms** while a 100,000-record retrain runs |
| Initial JS bundle, gzipped | < 200 KB | **178.4 KB** |
| Initial page load (LCP, 4G) | < 1.5 s | measured with the production stack (Phase 9 item 10) |
| Lighthouse Performance / Accessibility | ≥ 95 / ≥ 95 | measured with the production stack (Phase 9 item 10) |

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
- **Section 13's load test** (50 reviewers deciding every 3 seconds) is Phase 9 item 8.
