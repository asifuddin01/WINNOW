# Winnow — Complete Build Guide

> **Winnow** — *separate the evidence from the noise.*
> A free, open, self-hostable platform for systematic, scoping and rapid reviews: import → deduplicate → screen → resolve → full-text → extract → appraise → report (PRISMA 2020).
>
> Created by **Asif** — [asifuddin.com](https://asifuddin.com)

This document is the single source of truth for building Winnow. It is written to be handed to **Claude Code** (or any developer) in an empty folder. Build it **phase by phase** (Section 17). Do not skip the acceptance criteria.

---

## Table of Contents

0. How to use this guide with Claude Code
1. Product vision & goals
2. Non-negotiable requirements (security, speed, UX)
3. Tech stack (and why)
4. System architecture
5. Repository structure
6. Data model (PostgreSQL schema)
7. Roles & permissions
8. Feature specifications (every feature, in detail)
9. Algorithms (dedup, ranking, kappa, PRISMA)
10. API specification
11. Frontend specification (pages, components, UX, shortcuts)
12. Security specification
13. Performance specification
14. Accessibility, responsiveness & i18n
15. Testing strategy
16. DevOps: local run, deployment, backups, monitoring
17. Build phases with acceptance criteria and ready-to-paste prompts
18. `CLAUDE.md` (project conventions file)
19. Branding, footer & legal
20. Future roadmap

---

## 0. How to use this guide with Claude Code

1. Create an empty folder, e.g. `winnow/`.
2. Put this file inside it as `WINNOW_BUILD_GUIDE.md`.
3. Create `CLAUDE.md` in the same folder with the content from **Section 18**.
4. Open Claude Code in that folder and paste the **Phase 0** prompt from Section 17.
5. After each phase: run the tests, try it in the browser, then paste the next phase prompt.
6. Never start a phase before the previous phase's acceptance criteria pass.

Prerequisites on your computer: **Docker Desktop**, **Git**, **Node.js 22 LTS**, **Python 3.12+**, and `make` (on Windows use WSL2).

---

## 1. Product vision & goals

**Problem:** Researchers doing systematic reviews rely on tools that lock essential features (more reviews, AI ranking, PRISMA, full-text, collaboration) behind subscriptions.

**Goal:** Build a tool that does everything a researcher needs for evidence screening — free, fast, secure, and self-hostable — and does it better:

| Area | Winnow target |
|---|---|
| Cost | Every feature free, unlimited reviews, unlimited collaborators |
| Speed | Next record appears in < 50 ms; 100,000-record imports in < 60 s |
| AI | Active-learning ranking (local, no data leaves the server) + optional LLM suggestions with reasons |
| Rigor | Blind screening, dual review, conflict resolution, Cohen's kappa, full audit trail, PRISMA 2020 |
| Beyond screening | Data extraction forms, risk-of-bias (RoB 2, ROBINS-I, NOS), exports for meta-analysis |
| Ownership | Runs on a laptop or your own server; your data stays yours |

**Primary users:** Students, researchers, librarians, clinicians, review teams.

**Core workflow:**
```
Create review → Define criteria & keywords → Import records → Deduplicate
→ Title/Abstract screening (blind, dual) → Resolve conflicts
→ Full-text screening (PDFs) → Resolve conflicts
→ Data extraction → Risk of bias → Export + PRISMA diagram
```

---

## 2. Non-negotiable requirements

### 2.1 Security (academic data, unpublished research)
- OWASP ASVS Level 2 compliance as the baseline.
- Every data access checks project membership and role **on the server**, in the query itself.
- Passwords: Argon2id. Optional TOTP 2FA (required for project owners if the instance admin enables it).
- Server-side sessions in HttpOnly, Secure, SameSite=Lax cookies. No tokens in localStorage.
- CSRF protection, strict Content-Security-Policy, rate limiting, upload validation + malware scan.
- Full, append-only audit log of every decision and permission change.
- Blind mode must be enforced by the API (a reviewer must never be able to fetch others' decisions while blind), not just hidden in the UI.

### 2.2 Speed (performance budgets — enforced by tests)
| Metric | Budget |
|---|---|
| Screening: next record after a decision | < 50 ms perceived (prefetched), API p95 < 80 ms |
| Record list (any filter, 100k records) | API p95 < 150 ms |
| Import 10,000 RIS records | < 10 s |
| Import 100,000 records | < 60 s (background job, live progress) |
| Deduplication, 50,000 records | < 30 s |
| Initial page load (LCP, 4G) | < 1.5 s |
| JS bundle (initial, gzipped) | < 200 KB |
| Lighthouse Performance / Accessibility | ≥ 95 / ≥ 95 |

### 2.3 Ease of use
- A first-time user can create a review, import a file and screen 10 records in under 3 minutes without reading docs.
- Everything in screening is keyboard-driven (see 11.4). Mouse optional.
- Every destructive action is undoable or confirmed.
- Works on phone, tablet and desktop (screening on a phone must be comfortable: large tap targets, swipe gestures).
- Dark mode and light mode.

---

## 3. Tech stack (and why)

| Layer | Choice | Why |
|---|---|---|
| Backend language | **Python 3.12** | Best ecosystem for reference parsing, fuzzy matching and ML |
| API framework | **FastAPI** + **Pydantic v2** | Fast, typed, automatic OpenAPI docs |
| ORM / migrations | **SQLAlchemy 2.0 (async)** + **Alembic** | Mature, typed, safe parameterized queries |
| Database | **PostgreSQL 16** | Full-text search (tsvector), JSONB, row-level security, reliability |
| Cache / queue / sessions | **Redis 7** | Sessions, rate limits, job queue, pub/sub for live updates |
| Background jobs | **ARQ** (async Redis queue) | Lightweight, async, fits FastAPI |
| Fuzzy matching | **rapidfuzz** | Very fast C++ string similarity |
| Parsing | `rispy` (RIS), `bibtexparser` v2 (BibTeX), `lxml` (PubMed XML, EndNote XML), stdlib `csv` | Proven parsers |
| ML ranking | **scikit-learn** (TF-IDF + logistic regression / SGD); optional `sentence-transformers` embeddings | Fast, local, private |
| PDF | `pypdf` (server text extraction), **pdf.js** (browser viewer) | No external services |
| File storage | Local disk in dev; **S3-compatible** (MinIO self-hosted or any S3) in production | Swappable storage interface |
| Malware scanning | **ClamAV** (clamd container) | Scans every uploaded PDF |
| Frontend | **React 19 + TypeScript + Vite** (SPA) | Fast, simple, no SSR needed behind login |
| Routing | **TanStack Router** | Type-safe routes |
| Server state | **TanStack Query** | Caching, prefetching, optimistic updates |
| Virtualized lists | **TanStack Virtual** | Smooth 100k-row lists |
| Tables | **TanStack Table** | Sorting/filtering/column control |
| UI components | **Tailwind CSS v4** + **shadcn/ui** (Radix primitives) | Accessible, fast, consistent |
| Forms | **React Hook Form** + **Zod** | Typed validation shared with API types |
| Charts | **Recharts** | Progress & agreement charts |
| Icons | **lucide-react** | Clean, tree-shakeable |
| API types | `openapi-typescript` generated from FastAPI's OpenAPI | Frontend and backend never drift |
| Reverse proxy / TLS | **Caddy 2** | Automatic HTTPS, security headers |
| Containers | **Docker Compose** | One command to run everything |
| Tests | pytest, pytest-asyncio, httpx, Vitest, React Testing Library, **Playwright**, **k6** | Full coverage from unit to load |
| Lint/format | ruff + mypy (strict), ESLint + Prettier + tsc strict | Code quality gates |

Use the latest stable version of each at build time and pin exact versions in lockfiles (`uv.lock`, `pnpm-lock.yaml`). Use **uv** for Python packages and **pnpm** for Node.

---

## 4. System architecture

```
                   ┌────────────────────────────────────────┐
  Browser (SPA) ──►│ Caddy (HTTPS, security headers, gzip/br)│
                   └───────┬──────────────────────┬─────────┘
                           │ /api/*               │ /* (static SPA)
                           ▼                      ▼
                   ┌───────────────┐      ┌──────────────┐
                   │ FastAPI (api) │      │ web (static  │
                   │  uvicorn x N  │      │  build files)│
                   └──┬─────┬──────┘      └──────────────┘
                      │     │  enqueue jobs / sessions / pubsub
            SQL       │     ▼
                      │  ┌───────┐    ┌──────────────────────┐
                      │  │ Redis │◄──►│ worker (ARQ): import,│
                      │  └───────┘    │ dedup, ranking, PDF  │
                      ▼               │ text, exports, email │
               ┌────────────┐         └──────────┬───────────┘
               │ PostgreSQL │◄───────────────────┘
               └────────────┘
                      ▲
        ┌─────────────┴────────────┐
        │ Object storage (MinIO/S3)│◄── PDFs, import files, exports
        └──────────────────────────┘      (scanned by ClamAV first)
```

- **Live updates:** Server-Sent Events (SSE) at `/api/v1/projects/{id}/events` for import progress, conflict counts, collaborator activity. Backed by Redis pub/sub.
- **Stateless API:** can scale horizontally; all state in Postgres/Redis/storage.
- **Heavy work never blocks requests:** imports, dedup, model training, exports and PDF processing run in the worker.

---

## 5. Repository structure

```
winnow/
├── CLAUDE.md
├── WINNOW_BUILD_GUIDE.md
├── README.md
├── LICENSE                      # AGPL-3.0 recommended (keeps forks open)
├── Makefile                     # make dev, make test, make lint, make migrate, make seed
├── docker-compose.yml           # dev
├── docker-compose.prod.yml      # production
├── .env.example
├── Caddyfile
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py              # app factory, middleware, routers
│   │   ├── config.py            # pydantic-settings; all config from env
│   │   ├── db.py                # async engine, session dependency
│   │   ├── security/            # passwords, sessions, csrf, totp, rate_limit, permissions
│   │   ├── models/              # SQLAlchemy models (one file per aggregate)
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── api/v1/              # routers: auth, users, projects, members, imports,
│   │   │                        #   records, dedup, screening, conflicts, labels,
│   │   │                        #   fulltext, extraction, rob, prisma, exports,
│   │   │                        #   audit, events, admin
│   │   ├── services/            # business logic (no HTTP here)
│   │   ├── parsers/             # ris.py, bibtex.py, pubmed_xml.py, endnote_xml.py,
│   │   │                        #   csv_parser.py, nbib.py, common.py (normalization)
│   │   ├── dedup/               # blocking.py, scoring.py, clustering.py
│   │   ├── ranking/             # features.py, model.py, trainer.py
│   │   ├── prisma/              # counts.py, svg.py
│   │   ├── storage/             # base.py, local.py, s3.py
│   │   ├── workers/             # arq settings + job functions
│   │   └── email/               # templates + sender (SMTP)
│   └── tests/                   # unit/, integration/, security/, fixtures/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── routes/              # TanStack Router file routes
│       ├── api/                 # generated types + query hooks
│       ├── components/          # ui/ (shadcn), layout/, screening/, records/, charts/
│       ├── features/            # auth, projects, import, dedup, screening, conflicts,
│       │                        #   fulltext, extraction, rob, prisma, settings
│       ├── hooks/               # useHotkeys, useSSE, usePrefetchQueue...
│       ├── lib/                 # utils, highlight.ts, formatters
│       └── styles/
├── e2e/                         # Playwright tests
├── load/                        # k6 scripts
└── docs/                        # user guide, admin guide, security.md
```

---

## 6. Data model (PostgreSQL)

All primary keys are **UUIDv7** (time-ordered, index-friendly). All tables have `created_at timestamptz default now()`; mutable tables have `updated_at`. Soft-delete via `deleted_at` where noted.

### 6.1 Tables

```sql
-- USERS & AUTH
users (
  id uuid pk, email citext unique not null, name text not null,
  password_hash text not null,               -- argon2id
  email_verified_at timestamptz,
  totp_secret_enc bytea,                     -- encrypted with app key (AES-GCM)
  totp_enabled bool default false,
  recovery_codes_hash text[],                -- hashed one-time codes
  orcid text,                                -- optional
  is_instance_admin bool default false,
  failed_login_count int default 0, locked_until timestamptz,
  preferences jsonb default '{}',            -- theme, shortcuts, density
  created_at, updated_at, deleted_at
)
sessions               -- stored in Redis, not Postgres (key: sess:{random 256-bit id})
email_tokens (id, user_id fk, purpose enum('verify','reset','invite'), token_hash, expires_at, used_at)

-- PROJECTS (a "review")
projects (
  id uuid pk, owner_id fk users, title text not null, description text,
  review_type enum('systematic','scoping','rapid','umbrella','other'),
  research_question text, pico jsonb,        -- {population, intervention, comparator, outcome}
  status enum('setup','screening','fulltext','extraction','complete','archived'),
  settings jsonb not null,                   -- see 6.2
  created_at, updated_at, deleted_at
)
project_members (
  project_id fk, user_id fk, role enum('owner','admin','reviewer','viewer'),
  can_resolve_conflicts bool default false,
  stages text[] default '{title_abstract,full_text}',   -- which stages they screen
  joined_at, primary key(project_id,user_id)
)
project_invites (id, project_id, email, role, token_hash, invited_by, expires_at, accepted_at)

-- CRITERIA & KEYWORDS
criteria (id, project_id, kind enum('inclusion','exclusion'), text, position int)
keyword_groups (id, project_id, name, color text, kind enum('include','exclude','neutral'))
keywords (id, group_id fk, term text, is_regex bool default false, whole_word bool default true)
exclusion_reasons (id, project_id, label text, stage enum('title_abstract','full_text','both'), position int)
labels (id, project_id, name, color)

-- IMPORTS & RECORDS
import_batches (
  id, project_id, source_name text,          -- e.g. "PubMed 2026-09-20"
  database_name text,                        -- PubMed, Embase, Scopus, WoS, CINAHL, other
  file_key text, file_format enum('ris','bib','nbib','pubmed_xml','endnote_xml','csv'),
  status enum('queued','parsing','done','failed'), total int, imported int, errors jsonb,
  search_date date, search_string text,      -- recorded for PRISMA-S
  created_by, created_at
)
records (
  id uuid pk, project_id fk, import_batch_id fk,
  title text, abstract text, authors text[], year int, journal text,
  volume text, issue text, pages text, doi citext, pmid text, pmcid text, isbn text,
  url text, keywords text[], language text, publication_type text[],
  raw jsonb,                                 -- full original record
  title_norm text, doi_norm text,            -- for dedup (generated on insert)
  search_vector tsvector generated always as (
     setweight(to_tsvector('english', coalesce(title,'')),'A') ||
     setweight(to_tsvector('english', coalesce(abstract,'')),'B') ||
     setweight(to_tsvector('english', array_to_string(keywords,' ')),'C')) stored,
  duplicate_of uuid null fk records,         -- set when merged as a duplicate
  is_duplicate bool default false,
  ta_final enum('pending','included','excluded','conflict','maybe') default 'pending',
  ft_final enum('not_eligible','pending','included','excluded','conflict') default 'not_eligible',
  relevance_score real,                      -- latest model score 0..1
  created_at, updated_at
)

-- DEDUP
dup_clusters (id, project_id, status enum('pending','resolved','ignored'), score real, created_at)
dup_cluster_members (cluster_id fk, record_id fk, is_primary bool, primary key(cluster_id, record_id))

-- SCREENING
decisions (
  id, project_id, record_id fk, user_id fk,
  stage enum('title_abstract','full_text'),
  decision enum('include','exclude','maybe'),
  reason_ids uuid[], note text,
  time_spent_ms int,                         -- for analytics
  created_at, updated_at,
  unique(record_id, user_id, stage)
)
record_labels (record_id, label_id, user_id, primary key(record_id,label_id,user_id))
notes (id, record_id, user_id, body text, visibility enum('private','team'), created_at)
conflict_resolutions (
  id, project_id, record_id, stage, resolved_by fk users,
  final_decision enum('include','exclude'), reason_ids uuid[], note text, created_at
)

-- FULL TEXT
fulltexts (
  id, record_id fk unique, file_key text, filename text, size_bytes int, sha256 text,
  mime text, scan_status enum('pending','clean','infected','error'),
  text_extracted text, page_count int, uploaded_by, created_at
)
pdf_annotations (id, fulltext_id, user_id, page int, rects jsonb, color text, comment text, created_at)

-- EXTRACTION
extraction_forms (id, project_id, name, version int, schema jsonb, published bool, created_at)
extraction_entries (
  id, form_id, record_id, user_id, data jsonb,
  status enum('draft','submitted','verified'), created_at, updated_at,
  unique(form_id, record_id, user_id)
)
extraction_consensus (id, form_id, record_id, data jsonb, resolved_by, created_at)

-- RISK OF BIAS
rob_assessments (
  id, project_id, record_id, user_id, tool enum('rob2','robins_i','nos','quadas2','custom'),
  domains jsonb,            -- {domain_key: {judgement: 'low'|'some'|'high'|..., support: text}}
  overall text, status enum('draft','submitted'), created_at, updated_at
)

-- ML
ranking_models (id, project_id, stage, trained_at, n_labeled int, n_included int,
                metrics jsonb, artifact_key text, is_active bool)

-- AUDIT & ACTIVITY
audit_log (
  id bigserial pk, project_id uuid null, user_id uuid null, action text,
  entity_type text, entity_id uuid, before jsonb, after jsonb,
  ip inet, user_agent text, created_at
)  -- append-only: REVOKE UPDATE, DELETE from app role
notifications (id, user_id, kind, payload jsonb, read_at, created_at)
```

### 6.2 `projects.settings` JSON shape
```json
{
  "blind_mode": true,
  "reviewers_per_record_ta": 2,
  "reviewers_per_record_ft": 2,
  "maybe_counts_as": "include",
  "require_reason_on_exclude_ta": false,
  "require_reason_on_exclude_ft": true,
  "ranking_enabled": true,
  "llm_assist_enabled": false,
  "stopping_rule": {"type": "consecutive_excludes", "n": 200},
  "assignment": "all",
  "highlight_keywords": true
}
```

### 6.3 Required indexes
```sql
create index on records (project_id) where is_duplicate = false;
create index on records (project_id, ta_final);
create index on records (project_id, ft_final);
create index on records (project_id, relevance_score desc nulls last);
create index on records (project_id, doi_norm);
create index on records (project_id, pmid);
create index on records using gin (search_vector);
create index on records using gin (title_norm gin_trgm_ops);   -- pg_trgm extension
create index on decisions (project_id, stage, user_id);
create index on decisions (record_id, stage);
create index on audit_log (project_id, created_at desc);
```
Enable extensions: `citext`, `pg_trgm`, `pgcrypto`.

### 6.4 Derived state rule
`records.ta_final` / `ft_final` are recalculated in a single service function `recompute_record_status(record_id, stage)` whenever a decision or resolution changes — inside the same transaction. Logic:
1. If a conflict_resolution exists → use it.
2. Else if decisions count < reviewers required → `pending`.
3. Else if all decisions agree (with `maybe` mapped per `maybe_counts_as`) → that decision.
4. Else → `conflict`.
When `ta_final` becomes `included`, set `ft_final = 'pending'`.

---

## 7. Roles & permissions

| Action | Owner | Admin | Reviewer | Viewer |
|---|:-:|:-:|:-:|:-:|
| View project, records (subject to blind mode) | ✅ | ✅ | ✅ | ✅ |
| Screen / decide | ✅ | ✅ | ✅ | ❌ |
| See others' decisions while blind mode ON | ✅* | ✅* | ❌ | ❌ |
| Resolve conflicts | ✅ | ✅ | only if `can_resolve_conflicts` | ❌ |
| Import records, run dedup | ✅ | ✅ | ❌ | ❌ |
| Edit criteria, keywords, reasons, labels, forms | ✅ | ✅ | ❌ | ❌ |
| Invite/remove members, change roles | ✅ | ✅ (not owners) | ❌ | ❌ |
| Toggle blind mode, project settings | ✅ | ✅ | ❌ | ❌ |
| Export data, PRISMA | ✅ | ✅ | ✅ | ✅ |
| Delete / transfer project | ✅ | ❌ | ❌ | ❌ |

\* Owners/admins who also screen should be warned that viewing others' decisions breaks their own blinding; add a per-user toggle "Keep me blind too" (default ON).

Implementation: one central function `require_project_role(user, project_id, min_role, *, flag=None)` used as a FastAPI dependency on every project route. Every query on project data **must** filter by `project_id` obtained from the verified membership, never from untrusted input alone. Add a test that iterates over every route in the OpenAPI schema and asserts a non-member gets 404 (not 403, to avoid leaking existence).

---

## 8. Feature specifications

### 8.1 Accounts & authentication
- Sign up (name, email, password ≥ 12 chars, checked against a breached-password list via k-anonymity HIBP API, optional — configurable off for offline installs).
- Email verification required before joining projects (can be disabled for local single-user mode via `WINNOW_SINGLE_USER=true`, which auto-creates one admin and skips email).
- Log in, log out, log out all devices, active sessions list.
- Password reset by emailed one-time link (expires 30 min, single use).
- TOTP 2FA with QR code + 10 recovery codes.
- Account lockout: 10 failed attempts → 15 minutes lock; always constant-time responses.
- Optional "Sign in with ORCID" (OAuth2) — phase 9.
- Delete account (anonymizes decisions to "Former reviewer #n", keeps research integrity).

### 8.2 Projects (reviews)
- Dashboard of my reviews: cards showing title, role, progress bars (T/A, FT), conflicts count, last activity.
- Create wizard (3 steps): **Basics** (title, type, question/PICO) → **Criteria** (inclusion/exclusion list, keywords with colours, exclusion reasons pre-filled with sensible defaults: wrong population, wrong intervention, wrong comparator, wrong outcome, wrong study design, wrong publication type, not in language, duplicate, full text unavailable) → **Team** (invite by email, roles).
- Settings page: all of 6.2, danger zone (archive, transfer, delete with typed confirmation).
- Duplicate a project's setup (criteria, keywords, forms) as a template.

### 8.3 Import
- Drag-and-drop upload, multiple files at once, max 200 MB per file (configurable).
- Formats: **RIS**, **BibTeX**, **PubMed NBIB/MEDLINE**, **PubMed XML**, **EndNote XML**, **CSV** (with column mapping UI), **Zotero RDF** (phase 9).
- For each file, capture: source database name, search date, search string (optional; used in PRISMA and methods export).
- Preview first 5 parsed records before confirming.
- Runs as background job with live progress (SSE). Uses PostgreSQL `COPY` for bulk insert.
- Normalization on insert:
  - `doi_norm`: lowercase, strip `https://doi.org/`, `doi:` prefixes, trailing punctuation.
  - `title_norm`: lowercase, Unicode NFKD, strip accents, remove HTML tags, punctuation → space, collapse whitespace.
  - Authors to `Last, First` form; year as int (extract 4 digits).
  - Abstract: strip HTML/JATS tags, keep paragraphs.
- Errors per record are collected; the import succeeds partially and shows "12 records could not be read — download error report".
- Import history per project, with the ability to **undo an import** (deletes its records if no decisions exist, otherwise requires confirmation).

### 8.4 Deduplication
- Automatic after each import (configurable) plus a manual "Find duplicates" button.
- Algorithm in 9.1. Results grouped into clusters with a similarity score.
- Dedup review screen: side-by-side comparison of cluster members with differences highlighted; actions: **Merge (keep primary)**, **Not duplicates**, **Choose different primary**. Bulk action: "Auto-resolve all clusters with score ≥ 0.98 or exact DOI/PMID match".
- Merged duplicates are kept (flag `is_duplicate`, `duplicate_of`), never hard-deleted, and counted in PRISMA ("duplicates removed").
- Merging moves decisions/labels/notes from secondary to primary when present.

### 8.5 Title/Abstract screening (the heart of the app)
**Layout (desktop):** three panes.
- Left (collapsible): filters — status (pending/mine undecided/included/excluded/maybe/conflict), labels, import source, year range, keyword group hits, full-text search box. Counts next to each filter.
- Center: the record — title (large), authors, journal, year, DOI/PMID links (open in new tab with `rel="noopener noreferrer"`), abstract with keyword highlighting, keywords, publication type. Relevance score badge when ranking is on.
- Right: decision panel — Include / Maybe / Exclude buttons (colour + icon + text), exclusion reasons (checkbox chips), labels, notes (private/team), and (when not blind or when resolving) others' decisions.
- Top bar: progress ("1,284 / 5,902 screened by you · 42 conflicts"), sort order (relevance / random / year / title / import order), mode toggle **Focus mode** (one record, big text, no sidebars).

**Mobile layout:** single record card; swipe right = include, left = exclude, up = maybe; bottom sheet for reasons/labels; buttons also present (swipe must never be the only way).

**Behavior:**
- **Optimistic UI:** decision is shown instantly; the next record is already loaded (prefetch queue of the next 10 records). If the API fails, revert and show a toast with Retry.
- **Undo:** `Ctrl/Cmd+Z` or toast "Undo" reverts the last decision (within session, any time via history).
- **History panel:** list of my recent decisions; click to revisit and change.
- **Keyword highlighting:** done client-side with a single compiled regex per keyword group (escape user input; regex terms validated server-side for safety — max length, no catastrophic backtracking by using the `re2`-compatible subset; client uses a timeout-guarded matcher). Colours per group; a legend toggles groups on/off.
- **Time tracking:** measure time on each record (paused when tab hidden) → `time_spent_ms`.
- **Assignment modes:** `all` (every reviewer sees every record) or `split` (records distributed so each record gets exactly N reviewers, balanced).
- **Stopping rule helper** (ranking on): show "You have excluded 200 records in a row. Estimated remaining relevant: ~0–2 (see methods note)". Never auto-stop; it is advice only.
- **Bulk actions (owner/admin only, clearly logged):** e.g. exclude all records with publication type "Editorial". Requires confirmation and records `bulk=true` in the audit log.

### 8.6 Blind mode
- When ON: API endpoints for records/decisions return only the requesting user's own decisions. Aggregated counts that could reveal others' decisions (e.g., "included by 1 other") are hidden.
- Turning blind mode OFF is an owner/admin action, logged, and shows a confirmation explaining that it is typically done after screening finishes.

### 8.7 Conflicts
- Conflicts page lists all records with disagreeing decisions per stage, filterable by reviewer pair.
- Resolution view shows each reviewer's decision, reasons and notes side by side (blind mode is lifted for resolvers on this view only for these records).
- Resolver picks final Include/Exclude with reasons and note → `conflict_resolutions`.
- Option: "Discuss" — adds a team note and notifies the involved reviewers.

### 8.8 Full-text stage
- Records with `ta_final = included` enter the full-text queue.
- Upload PDF per record (drag-and-drop onto the record, or bulk upload a ZIP where filenames are matched by DOI/PMID/first author+year, with a matching review screen).
- "Find free full text" button: queries **Unpaywall** (by DOI, needs contact email in settings) and **PubMed Central** (by PMCID) → offers an open-access PDF link to download server-side. Configurable off for offline installs.
- PDF viewer (pdf.js) inside the app: search inside PDF, zoom, highlight + comment annotations, keyword highlighting.
- Same decision workflow as T/A, but exclusion reason is required by default.
- Mark "Full text not retrievable" → counted in PRISMA "reports not retrieved".

### 8.9 Labels, notes & search
- Labels: coloured tags, multi-apply, filter by label.
- Notes: private or team, markdown-lite (bold, italic, links) rendered safely (sanitized).
- Global search in a project: Postgres full-text search with prefix matching, plus exact DOI/PMID lookup. Search syntax: `"exact phrase"`, `-exclude`, `author:smith`, `year:2020..2024`, `label:rct`.

### 8.10 AI ranking (active learning, local)
- Once the project has ≥ 5 includes and ≥ 5 excludes at a stage, the worker trains a model (algorithm 9.2) and scores all pending records.
- Retrains automatically after every 25 new decisions (debounced; at most once per 60 s per project) and on demand.
- "Relevance" sort is the default once a model exists. A progress chart shows cumulative includes vs records screened (the "recall curve"), which makes screening efficiency visible.
- All ML runs on the server; no data leaves it.

### 8.11 Optional LLM assist (off by default)
- Admin configures a provider (Anthropic API key, or a local model through an OpenAI-compatible endpoint like Ollama).
- For a record, "Suggest" shows: suggested decision, which criteria it matches or fails, confidence, and a short rationale. It **never** records a decision on its own.
- A banner explains data is sent to the configured provider when enabled. Per-project opt-in by the owner. All suggestions stored for transparency and exportable (for reporting AI use in methods).

### 8.12 Data extraction
- Form builder: drag-and-drop fields — short text, long text, number (with unit), select, multi-select, yes/no/unclear, date, table (repeating rows, e.g., per-arm outcomes), section headers, help text.
- Forms are versioned; published forms are locked (new edits create a new version).
- Dual extraction optional; consensus view highlights differences field by field.
- Export extraction to CSV/XLSX in a long or wide format ready for R/RevMan/Stata.

### 8.13 Risk of bias
- Built-in templates: **RoB 2** (5 domains), **ROBINS-I** (7 domains), **Newcastle–Ottawa Scale**, **QUADAS-2**, plus custom templates.
- Per domain: judgement + support text. Signalling questions shown for guidance.
- Summary outputs: traffic-light table and weighted bar plot (SVG/PNG export).

### 8.14 PRISMA 2020 flow diagram
- Auto-computed counts (see 9.4) with manual override fields for items outside Winnow (e.g., records from citation searching, websites).
- Rendered as clean SVG following the PRISMA 2020 template; export SVG, PNG (300 dpi), PDF.

### 8.15 Analytics & reporting
- Progress per reviewer, per stage.
- **Inter-rater agreement:** Cohen's kappa per reviewer pair and overall (Fleiss' kappa for >2 reviewers), percent agreement (9.3).
- Time per record, decisions per day chart.
- **Methods text generator:** a paragraph describing the screening process with real numbers (e.g., "Two reviewers independently screened 5,902 titles and abstracts; agreement was κ = 0.81…"), editable before copying.

### 8.16 Exports
- Records with decisions: CSV, XLSX, RIS (with decision + reasons in notes/custom fields), BibTeX.
- Filters apply to exports (e.g., only included).
- Full project backup: ZIP containing JSON of everything + PDFs; **Import project backup** to restore on another Winnow instance.
- Audit log export (CSV).

### 8.17 Notifications & collaboration
- In-app notifications (conflict assigned, invite, mention in note, import finished).
- Optional email digests (daily) — off by default.
- Presence: "Sara is screening" indicator (no decision leakage in blind mode).

### 8.18 Admin (instance level)
- Users list, disable/enable user, reset 2FA, force logout.
- Instance settings: registration open/closed/invite-only, email SMTP, storage, Unpaywall email, LLM provider, max upload size.
- System health: queue length, worker status, disk usage, last backup.

---

## 9. Algorithms

### 9.1 Deduplication
```
Input: all non-duplicate records in project.
Step 1 — Exact keys (confidence 1.0):
   group by doi_norm (non-null), group by pmid (non-null).
Step 2 — Blocking (to avoid O(n²)):
   block key A = first 3 words of title_norm
   block key B = (year, first 10 chars of title_norm without spaces)
   block key C = pg_trgm similarity(title_norm) > 0.6 via index (for large sets)
Step 3 — Pairwise scoring within blocks:
   t = rapidfuzz.fuzz.token_sort_ratio(title_norm_a, title_norm_b) / 100
   a = first-author last name match (1/0.5/0)
   y = year equal → 1; differ by 1 → 0.7; else 0
   j = journal similarity (0..1) if both present else 0.5
   p = pages / volume equal → bonus 0.05
   score = 0.70*t + 0.12*a + 0.10*y + 0.08*j + p
   conflicting DOIs (both present and different) → score = 0 (never duplicates)
Step 4 — Pairs with score ≥ 0.90 → union-find into clusters.
Step 5 — Primary = most complete record (has DOI, abstract, most fields), tie → earliest import.
Step 6 — Auto-resolve clusters with exact DOI/PMID or score ≥ 0.98 if setting allows;
         others go to the manual review queue.
```
Test with a fixture of known duplicates (include tricky cases: erratum vs original, conference abstract vs full article with same title — should NOT auto-merge when DOIs differ).

### 9.2 Relevance ranking (active learning)
```
Features: TF-IDF on (title ×2 weight + abstract + keywords), word 1–2 grams,
          sublinear_tf, min_df=2, max_features=100k.
Model: LogisticRegression(class_weight='balanced', C=1.0, solver='liblinear')
Training labels: final decisions at that stage (include/maybe→1, exclude→0);
                 if not final yet, use majority of individual decisions.
Scoring: predict_proba for all pending records → records.relevance_score.
Metrics stored: n_labeled, n_included, cross-validated AUC when n ≥ 50.
Optional upgrade (setting): sentence-transformer embeddings (all-MiniLM-L6-v2)
          concatenated with TF-IDF; only if CPU budget allows.
Performance: vectorizer cached per project; 50k records must score in < 10 s.
```
Sort by relevance mixes in 5% random records (exploration) to reduce bias; disclose this in the UI tooltip.

### 9.3 Agreement
- Percent agreement = agreements / records both screened.
- Cohen's kappa: κ = (p_o − p_e) / (1 − p_e), computed on include vs exclude (maybe mapped per setting).
- Fleiss' kappa for ≥ 3 reviewers per record.
- Show interpretation band (Landis & Koch) with a note that bands are conventions.

### 9.4 PRISMA 2020 counts
```
Identification:
  records identified = sum(import_batches.imported) grouped by database_name
  + manual "other sources" counts
  duplicates removed = count(records where is_duplicate)
  records removed for other reasons = manual field
Screening:
  records screened = non-duplicate records
  records excluded (T/A) = count(ta_final = excluded)
  reports sought for retrieval = count(ta_final = included)
  reports not retrieved = count(full text marked not retrievable)
  reports assessed for eligibility = sought − not retrieved
  reports excluded with reasons = count(ft_final = excluded) grouped by reason
Included:
  studies included = count(ft_final = included)
```

---

## 10. API specification

Base path `/api/v1`. JSON only. Errors follow RFC 9457 (`application/problem+json`). All list endpoints use **cursor pagination** (`?cursor=&limit=`, max 200). All mutating endpoints require CSRF header `X-CSRF-Token`. OpenAPI docs at `/api/docs` in dev only.

```
AUTH
POST   /auth/register
POST   /auth/verify-email
POST   /auth/login                 {email, password, totp?}
POST   /auth/logout
POST   /auth/logout-all
POST   /auth/password/forgot
POST   /auth/password/reset
GET    /auth/me
GET    /auth/csrf
POST   /auth/2fa/setup   POST /auth/2fa/enable   POST /auth/2fa/disable
GET    /auth/sessions    DELETE /auth/sessions/{id}

PROJECTS
GET    /projects                   POST /projects
GET    /projects/{pid}             PATCH /projects/{pid}      DELETE /projects/{pid}
POST   /projects/{pid}/duplicate-setup
GET/POST/PATCH/DELETE /projects/{pid}/members[/{uid}]
POST   /projects/{pid}/invites     POST /invites/{token}/accept
CRUD   /projects/{pid}/criteria | keyword-groups | keywords | exclusion-reasons | labels

IMPORT
POST   /projects/{pid}/imports             (multipart upload → returns batch id)
GET    /projects/{pid}/imports/{bid}/preview
POST   /projects/{pid}/imports/{bid}/confirm
GET    /projects/{pid}/imports
DELETE /projects/{pid}/imports/{bid}        (undo)

RECORDS
GET    /projects/{pid}/records             ?status=&label=&q=&sort=&stage=&cursor=
GET    /projects/{pid}/records/{rid}
GET    /projects/{pid}/screening/queue     ?stage=&n=10   (next N for me, prefetch)
GET    /projects/{pid}/records/facets      (counts for filters)

DEDUP
POST   /projects/{pid}/dedup/run
GET    /projects/{pid}/dedup/clusters      ?status=pending
POST   /projects/{pid}/dedup/clusters/{cid}/merge     {primary_id}
POST   /projects/{pid}/dedup/clusters/{cid}/ignore
POST   /projects/{pid}/dedup/auto-resolve  {min_score}

SCREENING
PUT    /projects/{pid}/records/{rid}/decision   {stage, decision, reason_ids, note, time_spent_ms}
DELETE /projects/{pid}/records/{rid}/decision?stage=   (undo)
GET    /projects/{pid}/my-history          ?stage=
POST   /projects/{pid}/bulk-decision       (admin; filter + decision)
PUT    /projects/{pid}/records/{rid}/labels
POST   /projects/{pid}/records/{rid}/notes

CONFLICTS
GET    /projects/{pid}/conflicts           ?stage=
POST   /projects/{pid}/conflicts/{rid}/resolve  {stage, final_decision, reason_ids, note}

FULL TEXT
POST   /projects/{pid}/records/{rid}/fulltext        (upload PDF)
POST   /projects/{pid}/fulltext/bulk                  (ZIP)
GET    /projects/{pid}/records/{rid}/fulltext/url     (short-lived signed URL, 5 min)
POST   /projects/{pid}/records/{rid}/fulltext/find-oa
POST   /projects/{pid}/records/{rid}/fulltext/not-retrievable
CRUD   /projects/{pid}/fulltext/{fid}/annotations

RANKING / AI
POST   /projects/{pid}/ranking/train       GET /projects/{pid}/ranking/status
POST   /projects/{pid}/records/{rid}/llm-suggest

EXTRACTION & ROB
CRUD   /projects/{pid}/extraction-forms
GET/PUT /projects/{pid}/extraction-forms/{fid}/entries/{rid}
GET    /projects/{pid}/extraction-forms/{fid}/consensus/{rid}
CRUD   /projects/{pid}/rob/{rid}
GET    /projects/{pid}/rob/summary.svg

REPORTING
GET    /projects/{pid}/prisma              GET /projects/{pid}/prisma.svg|png|pdf
PATCH  /projects/{pid}/prisma/manual
GET    /projects/{pid}/stats               (progress, kappa, time)
GET    /projects/{pid}/methods-text
POST   /projects/{pid}/exports             {format, filters} → job id
GET    /projects/{pid}/exports/{eid}       (download when ready)
GET    /projects/{pid}/audit               ?cursor=

LIVE
GET    /projects/{pid}/events              (SSE)

ADMIN
GET    /admin/users   PATCH /admin/users/{uid}   GET/PATCH /admin/settings   GET /admin/health

HEALTH
GET    /healthz (liveness)   GET /readyz (db + redis check)
```

**Response example — screening queue item**
```json
{
  "id": "0192...",
  "title": "Effect of ...",
  "authors": ["Rahman, A.", "Chowdhury, S."],
  "year": 2023, "journal": "BMJ", "doi": "10.1136/...", "pmid": "37...",
  "abstract": "...",
  "keywords": ["..."],
  "relevance_score": 0.87,
  "my_decision": null,
  "labels": [],
  "others": null
}
```
(`others` is always `null` for blinded users.)

---

## 11. Frontend specification

### 11.1 Pages / routes
```
/login  /register  /forgot  /reset/:token  /verify/:token  /invite/:token
/                               → My reviews dashboard
/p/:pid                         → Project overview (progress, next action button)
/p/:pid/import                  → Import & history
/p/:pid/duplicates              → Dedup review
/p/:pid/screen/ta               → Title/abstract screening
/p/:pid/screen/ft               → Full-text screening
/p/:pid/records                 → Records table (all, filterable, bulk export)
/p/:pid/conflicts               → Conflicts
/p/:pid/extraction              → Forms & extraction
/p/:pid/rob                     → Risk of bias
/p/:pid/report                  → PRISMA, stats, kappa, methods text, exports
/p/:pid/settings                → Criteria, keywords, reasons, labels, team, settings
/account                        → Profile, security (2FA, sessions), preferences
/admin                          → Instance admin
```

### 11.2 Layout & navigation
- Left sidebar inside a project with icons + labels in workflow order: Overview · Import · Duplicates · Screen · Full text · Conflicts (badge) · Extraction · Risk of bias · Report · Settings. Collapsible to icons; becomes a bottom tab bar (5 main items + "More") on mobile.
- Project overview has one big **"Continue screening"** button that goes to the right stage.
- Command palette (`Ctrl/Cmd+K`): jump to any page, record by DOI/title, or action.
- Breadcrumbs on desktop; clear page titles everywhere.
- Global footer on every page (see Section 19).

### 11.3 Design system
- Tokens (CSS variables) for colour, spacing (4px scale), radius, shadows; light + dark themes; follow system preference by default, user can override.
- Semantic colours: Include = green, Exclude = red, Maybe = amber, Conflict = purple. Always paired with an icon and text (never colour only).
- Typography: Inter (UI) with system-font fallback; abstract text 17–18px, line-height 1.6, max width 75ch for readability. User-adjustable text size (S/M/L/XL).
- Density toggle (comfortable/compact) for tables.
- Skeleton loaders, not spinners, for page content. No layout shift.
- Empty states with a helpful next action (e.g., "No records yet — Import your first search results").

### 11.4 Keyboard shortcuts (screening)
| Key | Action |
|---|---|
| `I` or `1` | Include |
| `E` or `3` | Exclude |
| `M` or `2` | Maybe |
| `J` / `→` | Next record |
| `K` / `←` | Previous record |
| `R` | Open exclusion reasons (then number keys to toggle reasons) |
| `L` | Labels |
| `N` | Add note |
| `F` | Toggle focus mode |
| `H` | Toggle keyword highlighting |
| `/` | Search |
| `Ctrl/Cmd+Z` | Undo last decision |
| `?` | Show shortcuts help |
Shortcuts are customizable in account preferences and never fire while typing in inputs.

### 11.5 Performance rules for the frontend
- Route-level code splitting; the PDF viewer, form builder, charts load lazily.
- Prefetch the next 10 queue records; prefetch the next route on hover.
- Virtualize every list longer than 100 items.
- Optimistic mutations for decisions, labels, notes.
- Memoize the highlight regex per keyword-set version.
- No large dependencies (no moment.js, no lodash full import); bundle analyzer in CI with a size budget that fails the build.
- Service worker caches static assets (not API data).

### 11.6 Error handling
- Global error boundary with a friendly message and "Reload" + "Report" (copy error id).
- Network offline banner; decisions made offline are queued in memory and sent when back online (with a visible "3 decisions waiting to sync" indicator). Do not persist decisions in localStorage.
- Session expiry → modal to log in again without losing the current page.

---

## 12. Security specification

### 12.1 Authentication & sessions
- Argon2id (`argon2-cffi`): memory 64 MiB, time 3, parallelism 1. Rehash on login if parameters change.
- Session id: 256-bit random, stored in Redis with user id, created time, last seen, IP, UA; idle timeout 7 days (configurable), absolute timeout 30 days; rotate id on login and privilege change.
- Cookie: `__Host-winnow_session`, `HttpOnly; Secure; SameSite=Lax; Path=/`.
- CSRF: double-submit token (`/auth/csrf` issues token bound to session; required in `X-CSRF-Token` for non-GET). Also check `Origin` header matches.
- TOTP: RFC 6238, 30s window, ±1 step tolerance, replay protection (store last used step).
- Uniform error messages for login/reset ("If this email exists…").

### 12.2 Authorization
- Central permission dependency (Section 7) on every route. Default deny.
- IDOR protection: always load objects with `WHERE project_id = :verified_pid AND id = :id`.
- Optional defense in depth: PostgreSQL Row-Level Security policies keyed on `current_setting('app.user_id')` for `records`, `decisions`, `notes` — enable in phase 8.
- Blind mode enforced in the service layer; covered by dedicated tests.

### 12.3 Input & output safety
- Pydantic validation with max lengths on every string field (title 2,000, abstract 50,000, note 10,000, etc.).
- SQL only through SQLAlchemy parameterized queries; ban raw string SQL in lint rules (allow `text()` only with bound params, reviewed).
- XML parsing with `defusedxml` / lxml with `resolve_entities=False`, `no_network=True` (prevents XXE).
- CSV export: escape cells starting with `=`, `+`, `-`, `@`, tab, CR (prevent CSV/formula injection).
- Rendered notes/markdown sanitized with DOMPurify on the client; server stores raw text only.
- React escapes by default; `dangerouslySetInnerHTML` is forbidden except in the highlight component, which builds nodes rather than HTML strings.
- User-supplied regex keywords: validated for length ≤ 200 and a safe subset; matched with timeouts.

### 12.4 File uploads
- Allowed: import files by extension + content sniffing; PDFs by magic bytes `%PDF-`.
- Size limits enforced at Caddy and at the API.
- Store with random keys (never user filenames in paths); original filename saved in DB only.
- Scan every PDF with ClamAV before it becomes available (`scan_status`); infected → quarantined and admin notified.
- Serve files via short-lived signed URLs or streamed through the API with `Content-Disposition: attachment` for downloads and `inline` only for the PDF viewer, plus `X-Content-Type-Options: nosniff`.
- ZIP uploads: check for zip bombs (total uncompressed size limit, file count limit, path traversal names rejected).

### 12.5 HTTP security headers (Caddy)
```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; frame-ancestors 'none';
  object-src 'none'; base-uri 'self'; form-action 'self'; worker-src 'self' blob:
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cross-Origin-Opener-Policy: same-origin
```
(Self-host the Inter font so no external font requests are needed.)

### 12.6 Rate limiting (Redis sliding window)
- Login: 5/min per IP+email, 20/hour per IP.
- Password reset / register: 5/hour per IP.
- General API: 600/min per user. Uploads: 30/hour per user. LLM suggest: 60/hour per user.
- Return `429` with `Retry-After`.

### 12.7 Data protection
- TLS everywhere in production (Caddy auto-HTTPS).
- Secrets only from environment / Docker secrets; `.env` never committed; startup fails if `SECRET_KEY` is default or shorter than 32 bytes.
- TOTP secrets encrypted at rest (AES-256-GCM with key from env).
- Database and object storage not exposed publicly (internal Docker network only).
- Encrypted, automated daily backups (Section 16.4).
- Privacy: minimal personal data; account export and deletion; no third-party analytics or trackers by default.
- Logs never contain passwords, tokens, session ids or record abstracts.

### 12.8 Audit log
Logged actions (minimum): login success/failure, 2FA changes, member invite/role change/removal, settings changes, blind mode toggles, imports and undo, dedup merges, every decision create/update/delete, conflict resolutions, bulk actions, exports, deletions. The DB role used by the app has `INSERT, SELECT` only on `audit_log`.

### 12.9 Supply chain & CI security
- Dependabot/Renovate; `pip-audit` and `pnpm audit` in CI (fail on high severity).
- `bandit` (Python) and `semgrep` (OWASP rules) in CI.
- Container images: slim/distroless bases, run as non-root, read-only filesystem where possible, Trivy scan in CI.
- `gitleaks` pre-commit hook to prevent committing secrets.

### 12.10 Security tests (must exist)
- Non-member access to every project route → 404.
- Reviewer cannot read others' decisions in blind mode (records list, record detail, stats, exports, SSE events).
- Viewer cannot write anything.
- CSRF missing/invalid → 403.
- XXE payload in XML import is harmless.
- CSV formula injection escaped.
- Malicious PDF (EICAR test file) is quarantined.
- Session fixation: session id changes on login.
- Brute-force lockout works.

---

## 13. Performance specification

- **Database:** indexes in 6.3; `EXPLAIN ANALYZE` checked for all list queries on a 100k-record seed; no N+1 queries (use `selectinload`); connection pool sized to workers (pgbouncer optional for production).
- **Bulk operations:** `COPY` for imports; batched updates (1,000 rows) for scores and dedup.
- **Screening queue query:** select next N pending-for-me records using an anti-join on `decisions` with index support; cache facets for 5 s in Redis, invalidated on decisions.
- **Compression:** Brotli/gzip at Caddy. HTTP/2 and HTTP/3 enabled.
- **Caching:** static assets with hashed names cached 1 year (`immutable`); API responses `Cache-Control: no-store` for private data.
- **Uvicorn workers:** `2 × CPU cores`; worker processes separate from API.
- **Seed data script:** `make seed-large` generates a project with 100,000 realistic records for testing budgets.
- **Load test (k6):** 50 concurrent reviewers each deciding every 3 seconds for 10 minutes → p95 < 100 ms, error rate < 0.1%.

---

## 14. Accessibility, responsiveness & i18n

- WCAG 2.2 AA: contrast ≥ 4.5:1, visible focus rings, full keyboard support, ARIA via Radix primitives, skip-to-content link, `prefers-reduced-motion` respected, screen-reader announcements for decisions ("Included. Next record: …").
- Responsive breakpoints: 360px (small phone), 768px (tablet), 1024px, 1440px+. Test at each in Playwright.
- Touch targets ≥ 44×44 px.
- i18n-ready: all UI strings via `i18next`; English first; structure allows adding Bangla (বাংলা) and other languages later. Dates/numbers via `Intl`.
- Full Unicode support in records (non-English titles/abstracts display and search correctly; use `simple` text-search config as fallback for non-English).

---

## 15. Testing strategy

| Level | Tools | Target |
|---|---|---|
| Backend unit | pytest | Parsers, normalization, dedup scoring, kappa, PRISMA counts, permissions — ≥ 90% coverage of `services/`, `parsers/`, `dedup/`, `prisma/` |
| Backend integration | pytest + httpx + real Postgres/Redis (testcontainers or compose) | Every endpoint: happy path + auth + permissions |
| Security | pytest (Section 12.10), bandit, semgrep, ZAP baseline scan | All pass |
| Frontend unit | Vitest + React Testing Library | Hooks, highlight, reducers, forms |
| End-to-end | Playwright (Chromium, Firefox, WebKit; desktop + mobile viewport) | Full journey: register → create project → import RIS → dedup → dual screen with 2 users → resolve conflict → full text upload → PRISMA export |
| Accessibility | axe-core in Playwright | Zero serious/critical violations |
| Performance | k6 + Lighthouse CI | Budgets in 2.2 |

**Parser fixtures:** include real-world exports from PubMed, Embase (Ovid), Scopus, Web of Science, CINAHL, Cochrane Library, Zotero, EndNote, Mendeley, with messy cases (missing abstracts, HTML entities, multi-line fields, non-ASCII, BOM, Windows line endings).

CI (GitHub Actions): lint → typecheck → unit → integration → e2e → security scans → build images. Main branch protected; all checks must pass.

---

## 16. DevOps

### 16.1 Environment variables (`.env.example`)
```
WINNOW_ENV=development            # development | production
SECRET_KEY=change-me-to-64-random-chars
ENCRYPTION_KEY=base64-32-bytes
DATABASE_URL=postgresql+asyncpg://winnow:winnow@db:5432/winnow
REDIS_URL=redis://redis:6379/0
PUBLIC_URL=http://localhost:8080
WINNOW_SINGLE_USER=false
REGISTRATION=open                 # open | invite_only | closed
STORAGE_BACKEND=local             # local | s3
S3_ENDPOINT= S3_BUCKET= S3_ACCESS_KEY= S3_SECRET_KEY=
SMTP_HOST= SMTP_PORT=587 SMTP_USER= SMTP_PASSWORD= SMTP_FROM="Winnow <no-reply@example.com>"
CLAMAV_HOST=clamav
UNPAYWALL_EMAIL=
LLM_PROVIDER=none                 # none | anthropic | openai_compatible
LLM_API_KEY= LLM_BASE_URL= LLM_MODEL=
MAX_UPLOAD_MB=200
SESSION_IDLE_DAYS=7
```

### 16.2 Local development
```
make dev        # docker compose up: db, redis, clamav, minio, api (reload), worker, web (vite), caddy
make migrate    # alembic upgrade head
make seed       # demo project with 500 records and 2 demo users
make test       # all tests
open http://localhost:8080
```
Also provide `make local` — a **lightweight mode** without ClamAV/MinIO (local disk storage, scanning skipped with a clear warning) for low-RAM laptops.

### 16.3 Production deployment
- One VPS (min 2 vCPU, 4 GB RAM, 40 GB SSD) runs `docker-compose.prod.yml`: caddy, api, worker, db, redis, clamav, (minio or external S3).
- Point a domain (e.g., `winnow.asifuddin.com`) to the server; Caddy obtains HTTPS automatically.
- Deploy steps documented in `docs/deploy.md`: create server, install Docker, clone repo, copy `.env`, `make prod-up`, create first admin with `make create-admin`.
- Zero-downtime-ish updates: `make prod-update` (pull, build, migrate, restart api/worker).
- Firewall: only ports 80/443 (and SSH with key-only auth) open.

### 16.4 Backups & recovery
- Nightly `pg_dump` (custom format) + object storage sync, encrypted with `age`, kept 7 daily / 4 weekly / 6 monthly; optional off-site copy (any S3 bucket).
- `make restore BACKUP=...` documented and **tested in CI monthly** (restore into a fresh DB and run smoke tests).

### 16.5 Monitoring & logging
- Structured JSON logs (structlog) with request id; no sensitive fields.
- `/healthz`, `/readyz`; Docker healthchecks.
- Optional: Prometheus metrics endpoint (request latency, queue length, job duration) + Grafana dashboard; optional Sentry (self-hosted GlitchTip) for errors — both off by default.

---

## 17. Build phases (paste these prompts into Claude Code one at a time)

Each phase ends with: all tests green, lint/typecheck clean, the app runs with `make dev`, and a short `CHANGELOG.md` entry.

### Phase 0 — Foundation
**Prompt:**
> Read `WINNOW_BUILD_GUIDE.md` and `CLAUDE.md` fully. Build Phase 0: the repository structure from Section 5, Docker Compose dev environment (db, redis, api, worker, web, caddy), FastAPI app factory with config from env, Alembic setup, React+Vite+TS+Tailwind+shadcn/ui frontend with TanStack Router/Query, the app shell (sidebar, top bar, dark/light theme) and the global footer from Section 19. Add Makefile targets, `.env.example`, CI workflow with lint/typecheck/test, and health endpoints. Stop when Phase 0 acceptance criteria pass.

**Acceptance:** `make dev` starts everything; `http://localhost:8080` shows the shell with the footer "Built by Asif" linking to https://asifuddin.com; `/api/v1/healthz` returns ok; CI passes.

### Phase 1 — Auth & security core
> Build Phase 1: users, Argon2id passwords, Redis sessions with secure cookies, CSRF, login/register/logout/verify/reset flows, TOTP 2FA with recovery codes, rate limiting, lockout, security headers in Caddy, audit log table and service, single-user mode. Include all related tests from Section 12.10 that apply.

**Acceptance:** full auth flows work in the browser; security tests pass; session id rotates on login; 2FA works with an authenticator app.

### Phase 2 — Projects, team & settings
> Build Phase 2: projects, members, invites, roles and the central permission dependency (Section 7), create-project wizard, criteria, keyword groups, exclusion reasons (with defaults), labels, project settings, dashboard. Add the test that checks every project route returns 404 for non-members.

**Acceptance:** two users can collaborate on a project with correct permissions; all permission tests pass.

### Phase 3 — Import & records
> Build Phase 3: storage abstraction, upload endpoint, parsers for RIS, BibTeX, NBIB, PubMed XML, EndNote XML and CSV (with mapping UI), normalization, preview + confirm, background import with COPY and SSE progress, import history and undo, records table with virtualization, filters, full-text search syntax from 8.9. Create parser fixtures for the databases listed in Section 15.

**Acceptance:** 10k RIS imports in < 10 s; 100k in < 60 s with live progress; malformed records reported without failing the import.

### Phase 4 — Deduplication
> Build Phase 4: the dedup algorithm in 9.1 as a worker job, clusters, the side-by-side review UI, merge/ignore/choose primary, auto-resolve, decision migration on merge.

**Acceptance:** fixture of known duplicates reaches ≥ 97% precision and ≥ 95% recall; 50k records dedup in < 30 s.

### Phase 5 — Screening (T/A), blind mode, conflicts
> Build Phase 5: screening queue with prefetch, three-pane and focus layouts, mobile swipe layout, keyboard shortcuts (11.4), keyword highlighting, reasons, labels, notes, undo/history, time tracking, assignment modes, blind mode enforcement, status recomputation (6.4), conflicts page and resolution, bulk decisions for admins. Add E2E test with two reviewers.

**Acceptance:** next record appears instantly; blind mode security tests pass; two-reviewer E2E passes; works at 360px width.

### Phase 6 — AI ranking
> Build Phase 6: active-learning ranking (9.2) with automatic retraining, relevance sort with exploration, recall curve chart, stopping-rule helper. Then optional LLM assist (8.11) behind settings, off by default.

**Acceptance:** on a benchmark dataset (use a public labelled systematic review dataset such as those from the SYNERGY collection), relevance ordering finds 95% of includes after screening substantially fewer records than random order; report the numbers.

### Phase 7 — Full text
> Build Phase 7: PDF upload with ClamAV scanning, bulk ZIP matching, Unpaywall/PMC open-access finder, pdf.js viewer with search and annotations, full-text screening with required reasons, not-retrievable marking.

**Acceptance:** EICAR test file quarantined; ZIP bomb rejected; PDF viewer works on mobile.

### Phase 8 — Extraction, risk of bias, reporting
> Build Phase 8: extraction form builder with versioning, dual extraction and consensus, RoB templates (RoB 2, ROBINS-I, NOS, QUADAS-2) with traffic-light and summary plots, PRISMA 2020 diagram (SVG/PNG/PDF), stats with Cohen's/Fleiss' kappa, methods text generator, all exports including full project backup and restore, audit log viewer. Enable PostgreSQL RLS as defense in depth.

**Acceptance:** PRISMA numbers match a hand-calculated fixture; kappa matches a reference implementation; backup from one instance restores into another.

### Phase 9 — Polish, hardening & launch
> Build Phase 9: command palette, notifications, presence, admin panel, i18n setup, accessibility audit fixes, performance audit against Section 2.2 budgets with `make seed-large`, k6 load test, OWASP ZAP baseline scan, production compose file, backup/restore scripts, deploy docs, user guide in `docs/`. Optional: ORCID login, Zotero RDF import.

**Acceptance:** every budget in 2.2 met and reported; zero critical/serious axe violations; ZAP baseline has no high findings; restore test passes.

---

## 18. `CLAUDE.md` (create this file in the project root)

```markdown
# Winnow — project conventions for Claude Code

Read WINNOW_BUILD_GUIDE.md before any work. Build only the current phase.

## Rules
- Security first: every project route uses require_project_role; filter every query by verified project_id; non-members get 404.
- Blind mode is enforced in services, never only in UI.
- No raw SQL string building. No secrets in code. No tokens in localStorage.
- Every feature ships with tests; keep coverage targets from Section 15.
- Respect performance budgets (Section 2.2). Virtualize long lists. Background jobs for heavy work.
- Types: mypy --strict, tsc strict. Lint: ruff, eslint. Format: ruff format, prettier.
- Regenerate frontend API types after any API change: `make api-types`.
- Accessibility: keyboard reachable, labelled controls, never colour-only meaning.
- The footer "Built by Asif" linking to https://asifuddin.com must appear on every page, including login and error pages. Never remove it.
- Small, focused commits with clear messages. Update CHANGELOG.md each phase.
- When a requirement is ambiguous, choose the more secure and simpler option and note it in docs/decisions.md.

## Commands
make dev | make test | make lint | make migrate | make seed | make seed-large | make api-types
```

---

## 19. Branding, footer & legal

### 19.1 Name & identity
- **Name:** Winnow
- **Tagline:** *Separate the evidence from the noise.*
- **Logo idea:** a simple wheat stalk or sieve mark in a single colour; wordmark "winnow" in lowercase.
- **Primary colour:** deep teal `#0F766E` (accent), neutral slate greys; semantic colours per 11.3.
- Before publishing publicly, check that the name and your chosen domain are available and not trademarked in your field; if needed, alternatives: **Sievra**, **Siftwise**, **Chaffless**.

### 19.2 Footer (required on every page)
Text: **Built by Asif** — where "Asif" links to `https://asifuddin.com`.

```tsx
// frontend/src/components/layout/Footer.tsx
export function Footer() {
  return (
    <footer className="border-t border-border py-4 text-center text-sm text-muted-foreground">
      <span>
        Winnow · Built by{" "}
        <a
          href="https://asifuddin.com"
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-2"
        >
          Asif
        </a>
      </span>
    </footer>
  );
}
```
- Rendered in the root layout so it appears on all routes (including auth and error pages).
- In focus/screening mode on mobile, the footer sits below the content (not fixed) so it never covers decision buttons.
- The CSP in 12.5 allows this link (links are not restricted by CSP).
- Add a Playwright test asserting the footer link exists with `href="https://asifuddin.com"` on the dashboard, login, screening and error pages.

### 19.3 Legal
- Do not copy Rayyan's (or any other product's) name, logo, visual design, text or code. Winnow is an original product.
- License: **AGPL-3.0** recommended for the source code (anyone running a modified public version must share changes). Choose MIT if you prefer maximum permissiveness.
- Add `docs/privacy.md` and `docs/terms.md` templates before public launch; if hosting for others, state what data is stored, where, and how to delete it.
- Third-party services (Unpaywall, LLM providers) are optional and disclosed in the UI when enabled.

---

## 20. Future roadmap (after v1)
- Living reviews: scheduled re-running of saved PubMed searches (E-utilities) with new records flagged.
- Citation chasing (forward/backward via OpenAlex API).
- Meta-analysis module (effect sizes, forest plots) or R export templates for `metafor`.
- GRADE evidence profiles / Summary of Findings tables.
- Desktop app packaging (Tauri) for fully offline single-user use.
- Real-time co-editing for extraction forms.
