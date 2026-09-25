# AGENTS.md — rules for Codex in the Winnow project

Read `WINNOW_BUILD_GUIDE.md` (especially Section 9) and `CLAUDE.md` before you write
anything. Every rule in `CLAUDE.md` applies to you: security first, tests with every
feature, `mypy --strict`, `ruff`, and the "Built by Asif" footer is never removed.

The repository is at `/Users/mdasifuddin/Web/WINNOW` on this machine.

## Two agents, one repository

Claude Code and Codex build Winnow at the same time. Claude Code builds the phases from
Section 17 in order (Phases 0–7 are done; Phase 8, extraction, risk of bias and reporting,
is being built) and owns `main`. You build **self-contained, pure modules** that Claude Code
wires into the app.

- Work only in your own git worktree on a `codex/<topic>` branch:
  ```bash
  cd /Users/mdasifuddin/Web/WINNOW
  git worktree add ../winnow-codex -b codex/dedup
  cd ../winnow-codex
  ```
- Never commit to `main`; never run `git merge`, `git rebase`, `git push --force`, or touch
  another branch. Push your branch and say so in `docs/codex-notes.md`; Claude Code merges.
- Never run `make dev`, `make up`, `docker compose`, or anything that binds a port: Claude
  Code's stack is running. Your modules are pure, so their tests need no database, no Redis
  and no containers.

## The code graph (read this before grepping)

The repository is indexed as a knowledge graph, so you can find code without reading files.
It is built from the AST — symbols, their files and line numbers, and what calls what —
and it lives in `graphify-out/` (git-ignored, ~2,200 symbols and ~6,300 edges over the
backend, frontend and tests).

```bash
graphify query "where is the permission check for project routes"   # BFS over the graph
graphify query "how are records normalised on import" --budget 1500
graphify path "SetupService" "ProjectAccess"                        # shortest path between two symbols
graphify explain "check_project_role"                               # plain-language node summary
```

Each hit prints `NODE <symbol> [src=<file> loc=L<line> community=<n>]`, so you can open
exactly the right place. If `graphify-out/graph.json` is missing or stale after you add
files, rebuild it with `/graphify . --update` — it needs no API key for code, and takes
about a minute. The graph is a map, not the truth: read the file before you rely on it.

## Files you own

Create and edit only these:

```
backend/app/dedup/            # deduplication (Section 9.1)
backend/app/stats/            # agreement: percent, Cohen's and Fleiss' kappa (9.3)
backend/app/prisma/           # PRISMA 2020 counts and the SVG renderer (9.4, 8.14)
backend/app/rob/              # risk-of-bias templates (RoB 2, ROBINS-I, NOS, QUADAS-2)
backend/app/extraction/       # extraction forms: schemas, entries, differences, export rows (8.12)
backend/app/exports/          # RIS and BibTeX writers, spreadsheet-safe cells (8.16)
backend/app/reporting/        # the methods-text generator (8.15)
backend/tests/unit/dedup/     backend/tests/unit/stats/
backend/tests/unit/prisma/    backend/tests/unit/rob/
backend/tests/unit/extraction/ backend/tests/unit/exports/ backend/tests/unit/reporting/
backend/tests/fixtures/dedup/ # your fixtures only
docs/codex-notes.md           # your notes, questions and hand-over reports
docs/reviews/                 # review reports on other people's code (read-only reviews)
```

Everything else is Claude Code's, in particular `backend/app/models/`, `api/`, `services/`,
`security/`, `schemas/`, `parsers/`, `storage/`, `workers/`, `main.py`, `config.py`,
`alembic/` (never write a migration), all of `frontend/`, `e2e/`, `docker-compose*.yml`,
`Caddyfile`, `Makefile`, `CLAUDE.md`, `WINNOW_BUILD_GUIDE.md`, `CHANGELOG.md`, `README.md`.

Dependency files are off limits too: `pyproject.toml`, `uv.lock`, `package.json`,
`pnpm-lock.yaml`. **No new dependencies.** The backend has only what is already in
`pyproject.toml` — there is no `rapidfuzz`, no `numpy`, no `scikit-learn`. Where Section 9
names a library you do not have, implement the same measure in the standard library
(`difflib`, `re`, `unicodedata`, `statistics`, `dataclasses`) and say so in your notes.

If a task looks like it needs a file you do not own, stop and write it under "Requests for
Claude Code" in `docs/codex-notes.md`.

## How your modules must look

- Pure Python 3.12. No database, no HTTP, no FastAPI, no SQLAlchemy, no imports from
  `app.models`, `app.services`, `app.api` or `app.config`. Depend on nothing outside your
  own package and the standard library.
- Inputs and outputs are plain frozen dataclasses (or `TypedDict`) defined in your own
  package, e.g. `app/dedup/types.py`. Claude Code writes the adapter that loads rows from
  the database and calls you.
- Deterministic: same input, same output, no clocks, no randomness, no I/O, no logging of
  record contents.
- Every public function has type hints, a docstring stating inputs, outputs and complexity,
  and a note when it deviates from the guide.
- Line length 100, `ruff format` style, British-English comments that say *why*.
- Tests: table-driven, real fixtures, edge cases named in the guide. Aim for ≥ 95% coverage
  of your own package; it must not drag the project below its 90% floor.

## Commands (run from `backend/` in your worktree)

```bash
uv sync                                   # first time only, in your worktree
uv run pytest tests/unit/<your_folder> -q
uv run ruff check app/<your_folder> tests/unit/<your_folder>
uv run ruff format --check app/<your_folder> tests/unit/<your_folder>
uv run mypy                               # the whole project, tests included: CI does
```

All four must pass before you commit. Do not run the whole suite (`uv run pytest` alone
needs the database Claude Code is using).

## Your queue, in order

Take one at a time, finish it, hand it over, then start the next.

### 1. `app/dedup/` — deduplication (guide 9.1)

Pure functions over a `RecordForDedup` dataclass you define (id, title, title_norm, authors,
year, journal, volume, issue, pages, doi_norm, pmid, abstract_present, imported_at).

- `normalise_title(title: str) -> str` — lowercase, strip punctuation and accents, collapse
  whitespace; the same normalisation the database column will hold.
- `blocks(records) -> dict[str, list[id]]` — the block keys in 9.1 Step 2 (first three words
  of the title, and (year, first ten characters without spaces)). The trigram block is the
  database's job; note that in your hand-over.
- `score_pair(a, b) -> float` — exactly the weighting in Step 3
  (`0.70*title + 0.12*author + 0.10*year + 0.08*journal + 0.05 pages/volume bonus`), with
  `difflib.SequenceMatcher` over sorted tokens standing in for
  `rapidfuzz.fuzz.token_sort_ratio`. Two different DOIs → score 0, never duplicates.
- `cluster(records, threshold=0.90) -> list[Cluster]` — union-find, each cluster carrying its
  members, its score and the primary chosen by Step 5 (most complete, ties to earliest
  import), plus `auto_resolvable: bool` for Step 6.
- Fixtures in `backend/tests/fixtures/dedup/` with the tricky cases the guide names: an
  erratum against its original, a conference abstract against the full article with the same
  title but different DOIs (**must not** cluster), different capitalisation and punctuation,
  accents, missing years, and a pair that differs only by page numbers.
- Report precision and recall over your fixture in `docs/codex-notes.md`; the guide wants
  ≥ 97% precision and ≥ 95% recall.

### 2. `app/stats/` — agreement (guide 9.3)

`percent_agreement`, `cohens_kappa`, `fleiss_kappa` over a small `Decision` dataclass
(record id, reviewer id, decision), with `maybe` mapped by a parameter, plus
`landis_koch(kappa) -> str` for the interpretation band. Handle the degenerate cases
explicitly (no overlap, one category only, `p_e == 1`) and test them against worked examples
from the literature, with the expected numbers written into the test.

### 3. `app/prisma/` — PRISMA 2020 (guide 9.4 and 8.14)

`counts(inputs) -> PrismaCounts` as arithmetic over a `PrismaInputs` dataclass (the numbers
Claude Code will read from the database), and `render_svg(counts) -> str` producing a clean,
accessible diagram: a `<title>`/`<desc>`, text as text (never paths), no external fonts, no
scripts, and every number escaped. Test against a hand-calculated fixture, and assert the SVG
parses with `xml.etree.ElementTree` and contains no `<script>`.

### 4. `app/rob/` — risk-of-bias templates

JSON templates for RoB 2, ROBINS-I, NOS and QUADAS-2 (domains, signalling questions, allowed
judgements), a loader that validates them at import time, and `summary(assessments)` folding
per-domain judgements into the traffic-light counts a plot needs. Data only — no plotting.

### 5. `app/extraction/` — extraction forms (guide 8.12), branch `codex/extraction`

The rules for a data-extraction form and what people type into it. Claude Code stores forms
(`extraction_forms`: name, version, `schema` as JSON, published) and entries (one per
form, record and person, `data` as JSON) and calls you to check and compare them.

- `types.py`: `FieldType = Literal["short_text", "long_text", "number", "select",
  "multi_select", "yes_no_unclear", "date", "table", "section"]`; frozen dataclasses
  `Field(key, label, type, help=None, required=False, options=(), unit=None,
  integer=False, minimum=None, maximum=None, columns=(), min_rows=0, max_rows=None)` and
  `FormSchema(fields: tuple[Field, ...])`. A `table` field's `columns` are Fields of the
  scalar types (not table or section); a `section` is a heading and holds no value.
- `parse_schema(raw: object) -> FormSchema` and `schema_to_json(schema) -> dict` (round
  trip). Refuse, with every problem listed (`SchemaError(problems: list[str])`): keys not
  matching `[a-z][a-z0-9_]{0,39}` or repeated (table column keys unique within the
  table), empty or repeated options, options on types that take none, a table without
  columns, more than 200 fields, 100 options, 30 columns, labels over 300 characters or
  help over 2,000.
- `validate_entry(schema, data: object, *, complete: bool) -> dict[str, object]` returns
  the normalised data or raises `EntryError(problems: dict[str, str])` keyed by field
  (`"outcomes[2].mean"` for a table cell). Unknown keys are refused. Required fields are
  enforced only when `complete=True` (submitting); drafts may be partial. Normalise: text
  stripped, capped (short 500, long 20,000 characters); numbers as `int` when `integer`,
  else `float`, finite, within minimum/maximum; select values must be one of the options;
  multi-select a list in option order, no repeats; yes/no/unclear one of `"yes"`, `"no"`,
  `"unclear"`; dates ISO `YYYY-MM-DD` and real; tables a list of row dicts, within
  min/max rows, each cell validated like a scalar field. Empty values are dropped.
- `differences(schema, a: dict, b: dict) -> list[Difference]` for the consensus view:
  `Difference(path, label, a, b)` for every field whose normalised values differ, table
  cells compared row by row (`path="outcomes[1].n"`), in form order. Two empty values do
  not differ.
- `long_rows(schema, entries: Sequence[EntryForExport]) -> list[dict[str, object]]` and
  `wide_rows(...)` for export, where `EntryForExport(record_id, record_label, extractor,
  data)` (extractor is a name, or `"consensus"`). Long: one row per value (record,
  extractor, field key, field label, table row number or empty, column key, value, unit);
  multi-select joined with `"; "`. Wide: one row per entry, a column per scalar field
  key, table cells as `key[1].column` up to the largest row count present, then a header
  list you return beside the rows. Sections produce nothing.
- Tests: every field type accepted and refused, drafts versus complete, table limits,
  differences on nested cells, long and wide round-ups on a small multi-arm trial
  fixture. ≥ 95% coverage of the package.

### 6. `app/exports/` — citation writers (guide 8.16), branch `codex/exports`

- `types.py`: frozen `ExportRecord(id, title, abstract, authors: tuple[str, ...], year,
  journal, volume, issue, pages, doi, pmid, pmcid, url, keywords: tuple[str, ...],
  publication_type: tuple[str, ...], language, ta_status, ft_status, ta_reasons:
  tuple[str, ...], ft_reasons: tuple[str, ...], labels: tuple[str, ...])`; statuses are
  the strings Winnow stores (`included`, `excluded`, `pending`, `conflict`,
  `not_eligible`, `not_retrievable`, `maybe`), any may be `None`.
- `write_ris(records: Iterable[ExportRecord]) -> str`: `TY  - JOUR` (or `GEN` when no
  journal), `TI`, one `AU` per author, `PY`, `JO`, `VL`, `IS`, `SP`/`EP` split from
  pages, `DO`, `AN` (PMID), `UR`, `KW` per keyword, `LA`, `AB`, then Winnow's decisions in
  `N1` ("Title/abstract: included" and the like, reasons after a colon) and in custom
  fields `C1` (title/abstract status), `C2` (full-text status), `C3` (reasons, `; `),
  `C4` (labels), `ER  - `. CRLF line ends are what reference managers expect; strip line
  breaks and control characters from values.
- `write_bibtex(records) -> str`: `@article` (or `@misc`), citation keys from first
  author's surname + year + a/b/c on clashes (ASCII only), braces balanced and LaTeX
  specials escaped, the same decision fields as `note` and `keywords`.
- `spreadsheet_safe(value: object) -> str`: a cell that cannot run as a formula in Excel
  or LibreOffice (prefix `'` to text starting with `=`, `+`, `-`, `@`, tab or carriage
  return) — used by the CSV and XLSX exports.
- Tests: round-trip the RIS through `app.parsers.ris` (read-only use of that module is
  fine) and the BibTeX through `app.parsers.bibtex`, so what Winnow writes it can read;
  special characters, missing fields, clashing keys, formula-looking titles.

### 7. `app/reporting/` — methods text (guide 8.15), branch `codex/reporting`

`methods_text(facts: MethodsFacts) -> str`: an editable paragraph (or two) describing
how the review was screened, with real numbers, like guide 8.15's example ("Two reviewers
independently screened 5,902 titles and abstracts; agreement was κ = 0.81 …").
`MethodsFacts` (frozen, every field optional where the review may not have it): databases
searched with their record counts and search dates, duplicates removed, records screened,
reviewers per record at each stage, whether screening was blind, per-stage agreement
(percent, Cohen's or Fleiss' kappa and its Landis–Koch band), conflicts and how they were
resolved (a third reviewer, discussion), whether relevance ranking ordered the screening
and whether screening stopped early by the stopping rule (with the rule), AI suggestions
used (provider, model, how many), full texts sought, not retrieved, assessed, excluded
with reasons (grouped counts), studies included, extraction done singly or in duplicate,
and the risk-of-bias tool. Never state something the facts do not hold: a missing fact
drops its sentence. Numbers with thousands separators; kappa to two decimals; British
spelling. Tests: a full review, a minimal one, singular and plural wording, and a review
with no full-text stage yet.

## Committing and handing over

- Small commits on your branch, messages prefixed `codex:` (`codex: add Cohen's kappa`).
- After each task, append to `docs/codex-notes.md`: what you built, the public functions with
  their signatures, exactly how Claude Code should call them, what you deviated from and why,
  measured numbers (precision/recall, timings), and any open questions.
- Never edit another agent's section of that file; append at the end under a dated heading.
