# AGENTS.md — rules for Codex in the Winnow project

Read `WINNOW_BUILD_GUIDE.md` (especially Section 9) and `CLAUDE.md` before you write
anything. Every rule in `CLAUDE.md` applies to you: security first, tests with every
feature, `mypy --strict`, `ruff`, and the "Built by Asif" footer is never removed.

The repository is at `/Users/mdasifuddin/Web/WINNOW` on this machine.

## Two agents, one repository

Claude Code and Codex build Winnow at the same time. Claude Code builds the phases from
Section 17 in order (Phases 0–2 are done; Phase 3, import and records, is next) and owns
`main`. You build **self-contained, pure modules** from Section 9 that Claude Code wires
into the app later.

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
backend/tests/unit/dedup/     backend/tests/unit/stats/
backend/tests/unit/prisma/    backend/tests/unit/rob/
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

## Committing and handing over

- Small commits on your branch, messages prefixed `codex:` (`codex: add Cohen's kappa`).
- After each task, append to `docs/codex-notes.md`: what you built, the public functions with
  their signatures, exactly how Claude Code should call them, what you deviated from and why,
  measured numbers (precision/recall, timings), and any open questions.
- Never edit another agent's section of that file; append at the end under a dated heading.
