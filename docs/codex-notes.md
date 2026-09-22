# Codex notes

Codex works in its own worktree on `codex/…` branches and builds the pure modules from
guide Section 9 (see `AGENTS.md`). This file is its hand-over to Claude Code: what was
built, how to call it, what it deviates from, and what it needs.

Append a dated heading per task; never edit an earlier entry.

## Requests for Claude Code

_(nothing yet)_

## 2026-09-23 — Deduplication (guide 9.1)

### Built

- Added the pure `app.dedup` package with frozen, slotted `RecordForDedup` and `Cluster`
  dataclasses, Unicode/HTML-safe title normalisation, namespaced block keys, weighted
  pairwise scoring, exact DOI/PMID matching, deterministic union-find clustering,
  conservative cluster confidence, primary selection and auto-resolution eligibility.
- A component-level DOI guard prevents a DOI-less record from joining records with two
  conflicting DOIs transitively. If such a bridge is ambiguous, its surviving cluster is
  always sent to manual review.
- Added a 17-record JSON acceptance fixture and table-driven tests for erratum versus
  original, conference abstract versus full article, case/punctuation/accent variants,
  missing years, page-number variants, exact identifiers, weak same-block negatives,
  score symmetry and threshold floating-point boundaries.

### Public API and adapter call

- `normalise_title(title: str) -> str`
- `blocks(records: Sequence[RecordForDedup]) -> dict[str, list[uuid.UUID]]`
- `score_pair(left: RecordForDedup, right: RecordForDedup) -> float`
- `cluster(records: Sequence[RecordForDedup], threshold: float = 0.90) -> list[Cluster]`

Load one already-authorised project's non-duplicate rows, then call the package like this:

```python
from app.dedup import RecordForDedup, cluster

records = tuple(
    RecordForDedup(
        id=row.id,
        title=row.title or "",
        title_norm=row.title_norm or "",
        authors=tuple(row.authors or ()),
        year=row.year,
        journal=row.journal,
        volume=row.volume,
        issue=row.issue,
        pages=row.pages,
        doi_norm=row.doi_norm,
        pmid=row.pmid,
        abstract_present=bool(row.abstract and row.abstract.strip()),
        imported_at=row.created_at,
    )
    for row in rows
)
candidate_clusters = cluster(records)
```

`cluster()` returns non-singletons only. `Cluster.members` and `primary_id` are UUIDs;
`score` is the weakest selected union edge and is deliberately unrounded (range 0–1.05);
`auto_resolvable` is eligibility only, so the adapter must still honour the project setting.
Persisting clusters, merging records and applying that setting remain Phase 4 concerns.

### Deliberate substitutions and resolved ambiguities

- RapidFuzz is not installed. `score_pair()` uses the required standard-library
  `difflib.SequenceMatcher` over sorted normalised tokens. Its inputs are canonically
  ordered because `SequenceMatcher` itself can be directional; this preserves symmetric
  scores without a second comparison.
- `blocks()` implements keys A and B. PostgreSQL `pg_trgm` key C remains the database
  adapter's indexed job, as required by AGENTS.md.
- The guide's author value `0.5` means either first-author surname is missing; exact
  normalised surname match is `1`, mismatch is `0`. A missing year contributes `0`.
- Matching either nonblank pages or nonblank volume grants the single `0.05` bonus. The
  formula is not clamped, so a fully matching pair scores `1.05`.
- Records without a year omit block B rather than sharing a large null-year bucket; block A
  still finds same-title missing-year duplicates.
- Cluster score is the weakest deterministic spanning edge. Exact-only connectivity or a
  score of at least `0.98` is auto-resolve eligible unless a conflicting-DOI bridge was
  encountered.
- Primary selection prefers DOI, then abstract, then populated bibliographic fields, then
  earliest import; UUID is the final deterministic tie-break.

### Fixture quality and timings

- Pairwise fixture result: `TP=7`, `FP=0`, `FN=0`, `TN=129` over all 136 record pairs.
  Precision: **100%**. Recall: **100%**. This is an acceptance-fixture result, not an
  estimate of performance on unseen citations.
- `48` focused tests pass; scoped branch coverage is **98.89%**.
- Median clustering time for the 17-record fixture was **0.641 ms/call** across five batches
  of 1,000 calls on this machine.
- A pure in-memory 50,000-record synthetic corpus with well-distributed block keys completed
  in **0.552 s** with no database, Redis or containers. A deliberately skewed 500-record
  common block took **6.660 s**, confirming the documented `sum(block_size²)` worst case.

### Requests for Claude Code

- Phase 4 must add PostgreSQL trigram candidate block C and combine those candidates with
  this package's exact/A/B results. The current pure `cluster()` signature has no database
  candidate-pair hook; extend the adapter/package boundary deliberately rather than claiming
  block C is covered.
- Treat very large or skewed blocks explicitly (database trigram filtering, secondary
  blocking, or a reviewed cap). The 50k timing above meets the guide budget only for
  well-distributed blocks; the skew stress result must not be represented as a general 50k
  guarantee.

### Verification and delivery

- `uv run pytest tests/unit/dedup -q`
- `uv run ruff check app/dedup tests/unit/dedup`
- `uv run ruff format --check app/dedup tests/unit/dedup`
- `uv run mypy app/dedup`
- Extra coverage gate:
  `uv run pytest tests/unit/dedup -q --cov=app.dedup --cov-report=term-missing --cov-fail-under=95`
- Delivery branch: `codex/dedup`, pushed to `origin/codex/dedup` for Claude Code to merge.
