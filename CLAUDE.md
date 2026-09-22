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

## Finding code
- The repository is indexed as a knowledge graph in `graphify-out/` (git-ignored). Prefer
  `graphify query "<question>"`, `graphify path "A" "B"` and `graphify explain "<symbol>"`
  over grepping; each hit gives the file and line. Rebuild with `/graphify . --update`
  after large changes. Read the file before relying on what the graph says.

## Commands
make dev | make test | make lint | make migrate | make seed | make seed-large | make api-types