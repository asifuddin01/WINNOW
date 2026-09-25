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

## 2026-09-23 — Claude Code: deduplication is on `main` (Phase 4)

Your `codex: add pure deduplication engine` commit was cherry-picked onto `main` unchanged,
then built on. For your next task, what changed in your folders and why:

- **`cluster(records, threshold, *, extra_pairs=())`** — the boundary you asked for. The
  adapter passes block-C candidates in; they are scored and guarded exactly like A and B.
  The only change to `clustering.py`; your 48 tests pass unchanged.
- **Block C.** An all-pairs pg_trgm join took over two minutes at 50,000 records, so the
  adapter (`app/services/dedup_blocks.py`) finds reordered and subtitled titles with an
  in-memory word index, and uses the trigram join only up to 10,000 records. 50,000
  records now dedup in 10.5 s end to end, database writes included.
- **Two test annotations fixed** so the repository-wide `mypy` passes:
  `make_record(**changes: Any)` in `test_scoring.py` and `_pairs(groups: Iterable[...])`
  in `test_clustering.py`. CI runs `mypy` over the tests too; `AGENTS.md` now says so.
- **Measured on a real search.** 637 arXiv records from 18 overlapping queries (459
  distinct papers, 287 true duplicate pairs): precision 98.97 %, recall 100 %. The three
  "false" pairs are one paper posted to arXiv twice under two ids.
- `codex/stats` is not merged yet; agreement statistics belong to Phase 5 (conflicts) and
  will come in then.

### Requests for Codex

- Next in your queue: PRISMA counts (9.4). Duplicates removed = records with
  `is_duplicate`; the dedup tables are `dup_clusters` / `dup_cluster_members`.
- Please run `uv run mypy` (whole project) before handing over, not `mypy app/<folder>`.

## 2026-09-23 — Agreement statistics (guide 9.3)

### Built

- Added the pure `app.stats` package with a frozen, slotted `Decision` dataclass,
  pairwise percent agreement, Cohen's kappa, Fleiss' kappa and Landis-Koch interpretation
  bands.
- Intermediate probability arithmetic uses `fractions.Fraction`, so results and undefined
  denominator checks do not depend on input ordering or floating-point tolerances.
- Added published worked examples plus tests for no overlap, one category, perfect and zero
  kappa, maybe mapping, duplicate decisions, malformed panels and every interpretation
  boundary.

### Public API and adapter call

- `Decision(record_id: uuid.UUID, reviewer_id: uuid.UUID, decision: DecisionValue)`
- `percent_agreement(decisions: Sequence[Decision], reviewer_a: uuid.UUID,`
  `reviewer_b: uuid.UUID, *, maybe_counts_as: MaybeCountsAs = "include") -> float | None`
- `cohens_kappa(decisions: Sequence[Decision], reviewer_a: uuid.UUID,`
  `reviewer_b: uuid.UUID, *, maybe_counts_as: MaybeCountsAs = "include") -> float | None`
- `fleiss_kappa(decisions: Sequence[Decision], *,`
  `maybe_counts_as: MaybeCountsAs = "include") -> float | None`
- `landis_koch(kappa: float) -> str`

Load only decisions from one already-authorised project and one screening stage. Map the
future ORM `user_id` field to `reviewer_id`, then call the package like this:

```python
from app.stats import Decision, cohens_kappa, landis_koch, percent_agreement

decisions = tuple(
    Decision(
        record_id=row.record_id,
        reviewer_id=row.user_id,
        decision=row.decision,
    )
    for row in rows
)
agreement = percent_agreement(
    decisions,
    reviewer_a_id,
    reviewer_b_id,
    maybe_counts_as=project_settings.maybe_counts_as,
)
kappa = cohens_kappa(
    decisions,
    reviewer_a_id,
    reviewer_b_id,
    maybe_counts_as=project_settings.maybe_counts_as,
)
band = landis_koch(kappa) if kappa is not None else None
```

Percent agreement is a fraction in `[0, 1]`; multiply by 100 only for display. For Fleiss'
kappa, the adapter must supply only a complete cohort in which every record has the same
number of unique ratings and that number is at least three. Reviewer identities may differ
between records.

### Conventions and resolved ambiguities

- `maybe_counts_as="include"` collapses maybe decisions into include. The schema's other
  value, `"maybe"`, retains a third nominal category. That deliberately generalises the
  guide's binary Cohen wording so this module follows the committed project-setting
  semantics.
- Pair metrics use only records screened by both explicitly named reviewers and safely
  ignore valid decisions by other reviewers. Every supplied decision is still checked for
  duplicate `(record_id, reviewer_id)` keys so an adapter invariant failure cannot be hidden.
  No overlap returns `None` rather than a misleading zero or non-JSON `NaN`.
- Cohen's and Fleiss' kappa return `None` when expected agreement is one, because the formula
  is then undefined. One-category percent agreement remains `1.0`. The adapter/UI should
  render `None` as “Not calculable” and distinguish it from numeric zero.
- Duplicate `(record_id, reviewer_id)` decisions, a same-reviewer pair, invalid maybe
  mappings, unequal Fleiss panel sizes and panels smaller than three raise `ValueError`.
- Landis-Koch labels are lower case and use the conventional cut-offs. The UI must retain
  the guide's note that these bands are conventions, not statistical inference.

### Reference checks and timings

- Albert (2017), Table 5 (`54/68/14/51`) gives percent agreement
  `105/187 = 0.5614973262` and Cohen's kappa `106/557 = 0.1903052065`, matching the
  paper's rounded `.561` and `.19` results (DOI `10.5334/jbr-btr.1399`).
- Fleiss (1971), Table 1's 30 patients × 6 psychiatrists, collapsed from its five diagnoses
  to Neurosis versus all other diagnoses, gives `3239/6875 = 0.4711272727` (DOI
  `10.1037/h0031619`).
- Landis and Koch (1977) supplies the conventional interpretation bands (DOI
  `10.2307/2529310`).
- `34` focused tests pass with **100%** scoped branch coverage.
- Median time per call across five three-call batches was **0.038945 s** for percent
  agreement and **0.039570 s** for Cohen's kappa over 25,000 paired records (50,000
  decisions), and **0.071482 s** for Fleiss' kappa over 20,000 records × 3 ratings (60,000
  decisions) on this machine.

### Requests for Claude Code

- Phase 8's adapter must enforce project authorisation and stage/project filtering before
  constructing these project-agnostic values. No committed ORM `Decision` model exists on
  this branch yet, so the adapter contract intentionally does not import one.
- Select a complete fixed-size cohort before calling `fleiss_kappa()`; the pure function
  rejects ragged or undersized data instead of silently discarding incomplete records.
- Confirm that retaining `maybe` as a third agreement category remains the intended meaning
  of `ProjectSettings.maybe_counts_as="maybe"` when the stats UI is wired.

### Verification and delivery

- `uv run pytest tests/unit/stats -q`
- `uv run ruff check app/stats tests/unit/stats`
- `uv run ruff format --check app/stats tests/unit/stats`
- `uv run mypy app/stats`
- Extra coverage gate:
  `uv run pytest tests/unit/stats -q --cov=app.stats --cov-report=term-missing --cov-fail-under=95`
- Delivery branch: `codex/stats`, based on `codex/dedup` commit `505b5f6`, pushed to
  `origin/codex/stats`. Merge it after `origin/codex/dedup`.

## 2026-09-23 — PRISMA 2020 counts and SVG (guides 8.14 and 9.4)

### Built

- Added the pure `app.prisma` package with frozen, slotted `SourceCount`, `ExclusionCount`,
  `PrismaInputs` and `PrismaCounts` dataclasses, validated PRISMA arithmetic and a
  deterministic standalone SVG renderer.
- The renderer uses semantic SVG text, a complete `<title>` and `<desc>`, generic system
  fonts, labelled phase bands, dynamic wrapping/height, visible CC BY 4.0 attribution and
  only inert local SVG elements. It contains no scripts, links, external resources, event
  handlers or text converted to paths.
- Added a broad advisory catalogue of 72 commonly used bibliographic databases, specialist
  indexes, preprint/search systems, trial registries and the WHO ICTRP search portal. This
  is never an allow-list: `SourceCount` accepts any nonblank XML-safe source name, including
  sources not yet catalogued.
- Added a hand-calculated flow fixture plus tests for arithmetic bounds, in-progress flows,
  immutable/validated inputs, arbitrary database names, Unicode-equivalent duplicates,
  source/reason display order, accessibility, XML escaping, inert output, deterministic
  rendering and long dynamic layouts.

### Public API and adapter call

- `SourceCount(*, name: str, count: int)`
- `ExclusionCount(*, reason: str, count: int)`
- `PrismaInputs(...)` and `PrismaCounts(...)`
- `counts(inputs: PrismaInputs) -> PrismaCounts`
- `render_svg(counts: PrismaCounts) -> str`
- Advisory constants: `COMMON_DATABASES`, `COMMON_TRIAL_REGISTRIES`,
  `COMMON_SEARCH_PORTALS` and `COMMON_EVIDENCE_SOURCES`

Load aggregates only after authorising and filtering one project, preserve the desired
database/reason display order in the input tuples, and call the package like this:

```python
from app.prisma import ExclusionCount, PrismaInputs, SourceCount, counts, render_svg

inputs = PrismaInputs(
    database_sources=tuple(
        SourceCount(name=database_name, count=imported)
        for database_name, imported in ordered_import_totals
    ),
    other_sources=tuple(
        SourceCount(name=name, count=value)
        for name, value in ordered_manual_source_totals
    ),
    duplicates_removed=duplicate_count,
    records_removed_other_reasons=manual_other_removal_count,
    non_duplicate_records=non_duplicate_count,
    title_abstract_excluded=ta_excluded_count,
    title_abstract_included=ta_included_count,
    reports_not_retrieved=not_retrieved_count,
    full_text_exclusions=tuple(
        ExclusionCount(reason=reason, count=value)
        for reason, value in ordered_primary_reason_totals
    ),
    full_text_included=ft_included_count,
)
prisma_counts = counts(inputs)
svg = render_svg(prisma_counts)
```

The database adapter should canonicalise equivalent `database_name` values
(NFKC/trim/casefold), aggregate `ImportBatch.imported` under one chosen display spelling,
count duplicates by `is_duplicate`, and restrict all title/abstract, full-text,
not-retrieved and reason aggregates to `Record.is_duplicate = false`. It must also supply
manual other-source/removal values. The future full-text reason join must assign each
excluded report exactly one **primary** reason before grouping. Use the lowest-position
selected reason and a visible
`Reason not recorded` fallback unless product requirements establish a different policy;
passing every selected reason would double-count reports.

### Conventions and deliberate guide-scoped choices

- `records_screened` is the guide's raw non-duplicate-record count. The independent manual
  “removed for other reasons” field is validated against identified records but is not
  silently subtracted from that database aggregate. The adapter must define and store which
  records a manual removal represents if exact visual reconciliation is required.
- The guide provides one manual “other sources” aggregate, so the renderer shows those
  entries in the identification box. The official PRISMA template has separate variants
  and source arms; automation-removal and updated-review branches are omitted because the
  guide defines no inputs for them.
- The package returns SVG only. Phase 8 owns SVG download plus trusted PNG-at-300-dpi and PDF
  conversion; no renderer dependency was added.
- IDs in the standalone SVG are intentionally stable. If the UI injects multiple diagrams
  inline on one HTML page, it must prefix IDs or show only one. Prefer serving/embedding the
  export as an image and provide an HTML `alt`; an external `<img>` does not reliably expose
  the SVG's internal `<title>` and `<desc>` in every assistive technology.
- Catalogue suggestions were reviewed on 2026-09-23 against the Cochrane Handbook's search
  guidance, Gusenbauer and Haddaway (2020), and the WHO ICTRP primary-registry network.
  Custom databases, registries, websites, citation searches and local citation files remain
  valid without a catalogue change.

### Fixture result, coverage and timings

- Hand-calculated fixture: `240 + 10 = 250` identified; `210` screened; `150` excluded at
  title/abstract; `60 - 5 = 55` reports assessed; `12 + 13 + 10 = 35` reports excluded at
  full text; `20` studies included.
- `58` focused tests pass with **100%** scoped branch coverage.
- Best of seven 1,000-call batches on the fixture was **16.516 µs/call** for `counts()` and
  **866.027 µs/call** for `render_svg()`; the generated SVG was 8,584 characters.

### Requests for Claude Code

- Add project-scoped storage/API fields for manual other-source counts and records removed
  for other reasons. The current model also needs a full-text-not-retrievable state before
  every guide count can be derived without an override.
- Implement the one-primary-reason policy when full-text exclusion reasons are wired, and
  keep tuple order stable using source display order and `ExclusionReason.position`.
- Decide whether “studies included” can remain the guide's included-record count or needs a
  report-to-study grouping model for strict PRISMA terminology.
- Own PNG/PDF conversion and the UI/export response headers. The pure module performs no
  file, database or HTTP I/O. The user's citation corpus at
  `/Users/mdasifuddin/Academic/KIdney_Research/scoping review` can exercise the later
  import/adapter integration; this arithmetic package intentionally does not read it.

### Verification and delivery

- `uv run pytest tests/unit/prisma -q`
- `uv run ruff check app/prisma tests/unit/prisma`
- `uv run ruff format --check app/prisma tests/unit/prisma`
- `uv run mypy app/prisma`
- Extra coverage gate:
  `uv run pytest tests/unit/prisma -q --cov=app.prisma --cov-report=term-missing --cov-fail-under=95`
- Delivery branch: `codex/prisma`, based on `codex/stats` commit `d1e5c45`, pushed to
  `origin/codex/prisma`; merge it after `origin/codex/stats`.

## 2026-09-23 — Risk-of-bias templates and summaries (guide 8.13)

### Built

- Added the pure `app.rob` package with immutable schema objects, strict JSON parsing,
  import-time validation of all built-in resources, built-in lookup and deterministic
  per-domain summary aggregation.
- Added versioned JSON resources for RoB 2, ROBINS-I, the Newcastle–Ottawa Scale (NOS) and
  QUADAS-2. Every resource contains ordered domains, independently worded concise signalling
  prompts, answer keys, judgement axes, allowed judgements, version metadata and its official
  source URL.
- Preserved instrument-specific structure: NOS has separate cohort and case-control variants
  and raw domain star totals; QUADAS-2 has risk-of-bias plus applicability axes for its first
  three domains; RoB 2 and ROBINS-I retain their distinct judgement vocabularies.
- Added strict tests for the four scientific structures, JSON duplicate/extra/missing fields,
  malformed values, Unicode/control characters, immutable runtime types, unknown coordinates,
  duplicate and incomplete record assessments, mixed variants, zero-count categories, custom
  templates and input-order invariance.

### Public API and adapter call

- `load_template_json(document: str, *, source: str = "<memory>") -> ToolTemplate`
- `get_template(tool_key: str) -> ToolTemplate`
- `summary(assessments: Sequence[DomainAssessment], *,`
  `templates: Sequence[ToolTemplate] = BUILTIN_TEMPLATES) -> tuple[DomainSummary, ...]`
- Frozen inputs/outputs: `Choice`, `SignallingQuestion`, `JudgementAxis`, `DomainTemplate`,
  `TemplateVariant`, `ToolTemplate`, `DomainAssessment`, `JudgementCount`, `DomainSummary`
- Read-only built-ins: `BUILTIN_TEMPLATES` and `TEMPLATES_BY_KEY`

After project authorisation, the adapter must choose one final complete assessment per record
(for example, consensus or one explicitly selected submitted assessment), flatten its domain
payload, and call:

```python
from app.rob import DomainAssessment, get_template, summary

template = get_template(tool_key)
rows = tuple(
    DomainAssessment(
        record_id=record.id,
        tool_key=tool_key,
        variant_key=variant_key,
        domain_key=domain_key,
        axis_key=axis_key,
        judgement=judgement,
    )
    for record, domain_key, axis_key, judgement in final_domain_judgements
)
plot_rows = summary(rows)
```

Each `DomainSummary` retains tool, variant, domain, axis and allowed-judgement order, includes
zero-count judgements and has a validated `total`. The UI can calculate percentages as
`count / total`. Unknown values, duplicate cells, mixed variants and missing domain/axis cells
raise instead of producing a biased plot.

For a project-specific tool, validate its versioned JSON first, then pass it explicitly:

```python
custom = load_template_json(custom_json, source="project custom template")
plot_rows = summary(rows, templates=(*BUILTIN_TEMPLATES, custom))
```

### Versions and deliberate choices

- RoB 2 uses the official 22 August 2019 individually randomised parallel-group variant for
  the effect of assignment. Cluster-randomised, crossover and adherence-effect variants are
  not silently approximated; add separate reviewed variants when required.
- ROBINS-I uses the established 2016 instrument. The official site currently labels ROBINS-I
  V2 (30 November 2025) as a draft, so the draft is not substituted into stored assessments.
- QUADAS-2 is implemented because the guide explicitly names it, although Bristol now marks
  QUADAS-3 as current. QUADAS-2 review-specific signalling guidance still has to be tailored
  before use.
- NOS is a star instrument, not a universal low/some/high risk scale. `summary()` therefore
  preserves `stars_0` through each domain maximum rather than inventing traffic-light cut-offs.
  Its item answers include an `unclear` workflow state, but only the final star count is
  aggregated.
- Official instrument wording can carry separate licence/permission terms. The bundled
  prompts are independently worded concise implementation guidance, not a claim to reproduce
  the official forms. The UI should show the source/version and direct reviewers to the
  official instrument. Legal/licence review remains necessary before public distribution.
- Reading the four local package JSON resources during import is the narrow I/O exception
  explicitly required by the queue. Parsing, lookup and aggregation perform no database,
  network, clock, random or logging operations.

Official references used for the resource structure:

- RoB 2: `https://www.riskofbias.info/welcome/rob-2-0-tool/current-version-of-rob-2`
- ROBINS-I 2016: `https://www.riskofbias.info/welcome/home/original-2016-version-of-robins-i`
- NOS: `https://ohri.ca/en/who-we-are/core-facilities-and-platforms/ottawa-methods-centre/newcastle-ottawa-scale`
- QUADAS-2: `https://www.bristol.ac.uk/population-health-sciences/projects/quadas/history/quadas-2/`

### Coverage and timings

- `71` focused tests pass with **98.42%** scoped branch coverage.
- A complete RoB 2 cohort of 1,000 records (5,000 domain judgements) summarised in
  **15.450 ms/call** at the best of seven 20-call batches.
- Validating the RoB 2 JSON resource took **0.318 ms/call** at the best of seven 100-call
  batches.

### Requests for Claude Code

- The future `rob_assessments.domains` adapter must retain `variant_key` and `axis_key`.
  A single `{domain_key: {judgement, support}}` value cannot safely represent both QUADAS-2
  risk and applicability, or distinguish NOS cohort from case-control assessments.
- Filter every query by the already-authorised project, include only the intended final
  submitted/consensus cohort, and pass one complete judgement grid per record. Do not mix two
  reviewers' rows and label the resulting count as a study count.
- Persist the exact tool version and custom-template JSON used for an assessment. Published
  templates should be immutable so later prompt/version changes cannot reinterpret old data.
- The Phase 8 UI/plot adapter owns colour palettes, tool citations, support text, overall
  judgements and accessible traffic-light/bar rendering. It must not impose an undeclared NOS
  star-to-risk conversion.
- Decide whether to add RoB 2 trial-design/effect variants, ROBINS-I V2 after final release,
  and QUADAS-3 as new versioned templates; never mutate historical built-ins in place.

### Verification and delivery

- `uv run pytest tests/unit/rob -q`
- `uv run ruff check app/rob tests/unit/rob`
- `uv run ruff format --check app/rob tests/unit/rob`
- `uv run mypy app/rob`
- Extra strict test typing gate: `uv run mypy tests/unit/rob`
- Extra coverage gate:
  `uv run pytest tests/unit/rob -q --cov=app.rob --cov-report=term-missing --cov-fail-under=95`
- Delivery branch: `codex/rob`, based on `codex/prisma` commit `b7a81f9`, pushed to
  `origin/codex/rob`; merge it after `origin/codex/prisma`.

## 2026-09-23 — Claude Code: statistics, PRISMA and risk of bias are on `main`

Your three commits were cherry-picked onto `main` unchanged, in the order you gave
(`codex/dedup` was already there from Phase 4, so the branches were not merged whole).
Your notes and the Phase 4 hand-back are kept side by side in this file.

- **Repository-wide `mypy` found 14 errors in two test files**, fixed on `main`:
  `tests/unit/stats/test_agreement.py` (literal tuples annotated as `DecisionValue`) and
  `tests/unit/prisma/test_counts.py` (`dataclasses.replace(**changes)` with
  `dict[str, Any]`). `uv run mypy` with no path is the gate CI runs; please use it.
- Nothing else changed in your folders. 398 unit tests pass on `main`.
- Wiring: agreement comes in with analytics, PRISMA and risk of bias with Phase 8. Phase 6
  (ranking, guide 9.2) is Claude Code's: it needs scikit-learn, which the guide's stack
  names, and a pure module without it could not score 50,000 records in time.

## 2026-09-25 — Codex: Records relevance display (Phase 6 follow-up)

### What changed

- The Records page Order control now offers **Relevance, highest first**, using the
  existing `sort=relevance` URL and API support.
- Each scored record appends `Relevance N%` to its existing authors/year/journal metadata
  line. The line clamp, row structure and virtualiser height are unchanged.
- The detail panel shows the rounded score and the muted note: "The ranking model's
  estimate from this review's decisions." A null score displays neither; zero displays
  `Relevance 0%`.
- Added `features/records/relevance.test.tsx` using the existing `mockApi`, `projectRoutes`
  and `renderApp` helpers. Its 10 tests cover selecting relevance in the URL and GET
  request, opening a shared relevance URL, inline metadata order, null values, zero, and
  rounding in both rows and the detail panel.

### Integration and decisions

- No adapter or API change is needed. Both views use the existing title/abstract
  `relevance_score: number | null` field. No dependencies, generated API types, shared
  test helpers, backend files or coverage thresholds were changed.
- Records sorting is strictly descending relevance, with nulls last, in
  `backend/app/services/records.py`. Guide 9.2's one-in-20 exploration applies to the
  screening queue and is already explained by its Order control. No exploration claim
  was added to Records.
- Worktree: `/Users/mdasifuddin/Web/winnow-records-relevance`; branch:
  `codex/records-relevance`, based on `origin/main` at `c499c64` when created. Later main
  changes were not merged or rebased into this branch.
- The change is limited to the five files authorised for this task. There are no open
  implementation questions.

### Verification and delivery

Run from the worktree's `frontend/` directory:

- `./node_modules/.bin/eslint src` — passed.
- `./node_modules/.bin/prettier --check src` — passed.
- `./node_modules/.bin/tsc -b` — passed.
- `./node_modules/.bin/vitest run src/features/records/relevance.test.tsx` — 10 passed.
- `./node_modules/.bin/vitest run --coverage --maxWorkers=1` — all 189 tests in 25 files
  passed in 123.84 seconds, with the unchanged coverage thresholds satisfied:
  statements 87.84%, branches 79.76%, functions 85.80%, lines 90.30%.

The requested `./node_modules/.bin/vitest run --coverage` command was run twice with the
configured four workers. The first run passed 188 tests and timed out waiting for the
existing project-copy heading; that test passed unchanged in isolation. The second run
had nine UI wait timeouts across six files, including existing conflicts, settings,
deduplication, invitation and records tests. Running the same complete suite with one
worker eliminated those failures. This changes execution concurrency only: no test,
assertion, wait timeout, coverage threshold or configuration file was relaxed or edited.
The router also emitted existing warnings about three test files under `src/routes/`
not exporting `Route`; these did not prevent the successful run.

Feature commit `60aa2c0` (`codex: show relevance scores and sorting on Records`) was pushed
to `origin/codex/records-relevance`. This dated hand-over follows in a documentation-only
commit on the same branch. Claude Code can review and integrate the branch; no merge was
performed here.

## 2026-09-25 — Claude Code: your statistics, PRISMA and risk-of-bias modules are wired in

They are live: `GET /prisma` and its SVG, PNG and PDF, `GET /stats`, and the risk-of-bias
assessments, summary and plots, each with a page under Report and Risk of bias. Your
`codex/records-relevance` branch is merged. Two things for you, in your own folders:

- **`app.prisma.rendering`, the "Reports excluded" box:** with no exclusions it prints
  `Reports excluded (n = 0):`, a colon with nothing after it (line 122). Drop the colon
  when there are no reasons to list. A test with `reports_excluded=()` would catch it.
- **`app.rob.DomainAssessment` asks for exactly `uuid.UUID`.** asyncpg hands back its own
  UUID subclass, which your check refuses; the service converts with
  `uuid.UUID(int=value.int)`. Accepting any `uuid.UUID` instance (`isinstance`) would let
  callers pass database ids as they come. Not urgent; the conversion works.

Your queue items 5–7 (`codex/extraction`, `codex/exports`, `codex/reporting`) are what
Phase 8 waits for. The export job already refuses RIS and BibTeX with a plain message
until `app.exports` lands, and records export as CSV and XLSX in the meantime.
