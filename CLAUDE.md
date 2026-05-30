# CLAUDE.md — Cloud Cost Optimizer & Remediation Engine

You are the **engineer**. The human is the **architect**. This is a "vibe coding" build:
the human does not write or edit code. You provide all logic, all fixes, all tests.

Read `SPEC.md` before writing anything. It is the single source of truth for the data
model, the rules, the API contract, and the acceptance criteria.

## Non-negotiable workflow (the challenge grades these)

1. **Audit log.** After EVERY turn, append to `prompts.md`:
   - a `## Turn N — <short title>` heading,
   - the exact prompt the human just sent (verbatim, in a fenced block),
   - 2–4 bullets summarising what you did.
   Never skip this. If you forget, do it before anything else next turn.

2. **Time-check.** A build timer started at Turn 1. End EVERY response with a line:
   `⏱️ Elapsed Time: <Xh Ym>` (estimate from turn count / wall clock; goal MVP in 4–6h,
   hard cap 16h).

3. **Definition of Done** for any task — do not say a task is complete until ALL hold:
   - code implemented per the task's acceptance criteria,
   - the specified automated tests written,
   - `pytest` run and shown PASSING in your reply (paste the summary line),
   - `prompts.md` updated,
   - a conventional commit made (`feat:`, `test:`, `fix:`, `chore:`, `docs:`),
   - elapsed-time line printed.

4. **No real cloud, ever.** This tool is 100% offline. It parses *exported* billing files.
   It NEVER authenticates to AWS/Azure and NEVER executes any command. Remediation output
   is generated **command strings only**. No `boto3`/`azure-sdk` calls that hit a network.
   No secrets, no API keys, no `.env` with credentials.

## Stack & conventions

- Python 3.11+. Dependency/management: `uv` (fallback `pip` + venv). Single `pyproject.toml`.
- Web: **FastAPI** + **uvicorn**. API-first: the dashboard is just a client of the JSON API.
- DB: **SQLite** via **SQLAlchemy 2.0** (typed ORM, `Mapped[...]`). One file `app.db` (gitignored).
- Validation: **pydantic v2** for all request/response schemas.
- Tests: **pytest** + FastAPI `TestClient` (httpx). Fast, deterministic, no network, no sleeps.
- Lint/format: **ruff**. Type hints on every function. Keep functions small and pure where possible.
- Layout: see SPEC.md. Business logic lives in `app/`, never in route handlers beyond wiring.

## Skills available in this repo (use them)

- **python-implementation** — consult when writing/extending app code (routes, models, parsers, rules).
- **pytest-author** — consult when writing or fixing tests.
- **code-review** — consult at the end of each task and at final review, before declaring done.

## Per-task loop

Implement → write tests for the acceptance criteria → run pytest → if red, fix (you, not me) →
when green, run the **code-review** skill on what changed → update `prompts.md` → commit →
print elapsed time. Build vertical slices: one rule working end-to-end through the API before
adding breadth. Do not gold-plate; ship the MVP, note deferred ideas in README "Future work".
