# Prompts — Audit Log

## Turn 1 — Lead Architect kickoff (acknowledgment)

```
Lead Architect mode: ON. We are building a Python-based, API-first **Cloud Cost Optimizer & Remediation Engine** using a free database and a dashboard.
Rules:
- No Manual Edits: You provide all logic and fixes. I will not edit any code.
- Audit Log: You must maintain a file named prompts.md. After every turn, update that file (or provide the text block) with the prompt I just used.
- Time-Check: Start a timer. Goal is an MVP in 4-6 hours (Max window: 16h). Report 'Elapsed Time' at the end of every response. Acknowledge and let's start.
```

- Acknowledged the three operating rules (No Manual Edits, Audit Log, Time-Check).
- Started the build timer at Turn 1 (T = 0h 0m).
- Read `CLAUDE.md` (auto-loaded), `docs/SPEC.md`, `docs/PLAN.md`, and `docs/PROMPT_PLAYBOOK.md` to confirm the workflow and operating constraints.
- No code yet — Turn 2 will scaffold per `docs/PLAN.md` T0 / Playbook Prompt 2.

## Turn 2 — Task 0: Bootstrap & scaffold

```
Read CLAUDE.md and @SPEC.md fully, then acknowledge the architecture in 3-4 bullets (no code yet).
Then scaffold the project exactly per SPEC §3:
- pyproject.toml (uv-compatible) with fastapi, uvicorn, sqlalchemy>=2, pydantic>=2, python-multipart, pytest, httpx, ruff.
- The app/ package skeleton with empty-but-importable modules, app/db.py with init_db(), and
  app/main.py exposing GET /health -> {"status":"ok"}.
- tests/, data/, static/ folders. .gitignore (app.db, __pycache__, .venv).
- Initialise prompts.md with Turn 1 (the kickoff) and Turn 2 (this prompt) logged.
- git init + first conventional commit.
Use the python-implementer skill. Then write and run the health test. Show me the passing pytest
summary and elapsed time.
```

- Acknowledged the architecture in 4 bullets (API-first FastAPI; offline-only with no cloud SDKs; SQLite + SQLAlchemy 2.0 typed ORM with one `SessionLocal` and `get_db()`; vertical-slice delivery per PLAN T0–T8).
- Wrote `pyproject.toml` (PEP 621, uv-compatible) pinning the stack: fastapi, uvicorn[standard], sqlalchemy>=2, pydantic>=2, python-multipart; `[project.optional-dependencies] dev` = pytest, httpx, ruff. Configured ruff (line-length 100, py311, E/F/I/B/UP/SIM) and pytest (`testpaths=tests`, `pythonpath=.`).
- Scaffolded `app/` per SPEC §3: `main.py` (FastAPI factory + `GET /health` → `{"status":"ok"}`), `db.py` (SQLite engine, `SessionLocal`, typed `Base(DeclarativeBase)`, idempotent `init_db()`, `get_db()` generator dependency), plus empty-but-importable stubs for `models.py`, `schemas.py`, `services.py`, `remediation.py`, `ingestion/{normalize,aws_cur,azure}.py`, `rules/{base,catalog}.py`.
- Created `tests/`, `data/`, `static/` (with `.gitkeep`s), added `app.db`/`*.sqlite*` to `.gitignore` (`__pycache__/` and `.venv/` already present).
- Wrote `tests/test_health.py` using FastAPI `TestClient` (httpx) — asserts 200 + body `{"status":"ok"}`.
- Created `.venv`, installed `.[dev]`, ran `pytest` (green) and `ruff check .` (clean) — summary line shown in chat.
- Committed `feat(t0): scaffold project — fastapi /health, db layer, tests, prompts.md` as the first conventional commit on top of the existing `Cloud cost optimizer scaffold` docs commit.

## Turn 3 — Task 1: Domain model & DB layer

```
Implement app/models.py (SQLAlchemy 2.0 typed Mapped models: Scan, Resource, Finding per SPEC §4)
and wire init_db() in app/db.py to create tables. Add app/ingestion/normalize.py with the
NormalizedResource dataclass. No parsing/rules yet. Use the python-implementer skill, then the
test-author skill for the tests.
Write tests, run them, update prompts.md, commit, report elapsed time.
```

- Implemented `app/models.py` with three SQLAlchemy 2.0 typed `Mapped[...]` models per SPEC §4: `Scan` (id, created_at, source_filename, provider, resource_count, finding_count, total_monthly_savings), `Resource` (FK scan_id, provider, resource_id, resource_type, region, status, monthly_cost, attached, last_activity_date, tags JSON, raw JSON), `Finding` (FK scan_id + resource_pk, rule_id, title, reason, severity, estimated_monthly_savings, remediation_command, created_at). Wired bi-directional `relationship()` with `cascade="all, delete-orphan"` and `passive_deletes=True`; FKs declared `ON DELETE CASCADE`. Added indexes on hot lookup columns (`scan_id`, `resource_id`, `resource_type`, `rule_id`). `created_at` defaults via `datetime.now(UTC)` (`UTC` alias is Python 3.11+; ruff UP017 satisfied).
- `app/db.py` `init_db()` already imports `app.models` for side-effect registration; now that the models exist, `Base.metadata.create_all(engine)` will materialise all three tables.
- Wired `init_db()` into FastAPI startup via a `lifespan` async context manager in `app/main.py` (replaces the deprecated `on_event("startup")`). PLAN T1 acceptance: "tables created on startup" — satisfied.
- Added `app/ingestion/normalize.py` with `NormalizedResource` dataclass (`slots=True`): `provider` (Literal["aws","azure"]), `resource_id`, `resource_type`, `region`, `status`, `monthly_cost: float`, `attached: bool`, `last_activity_date: date | None`, `tags: dict[str,str]`, `raw: dict[str,Any]`. Mutable defaults via `field(default_factory=dict)`. Not frozen (parsers may set fields incrementally if needed; rule engine treats it as read-only by convention).
- Wrote `tests/test_models.py` with a module-level in-memory SQLite `engine` fixture (`sqlite://`) so tests never touch the real `app.db`. Two tests per PLAN T1: `test_create_all_creates_tables` (inspects DB and asserts `{scans, resources, findings}` exist) and `test_insert_and_read_finding` (inserts a Scan with one Resource and one Finding via ORM relationships in a Session, commits, opens a *fresh* Session and asserts every persisted field plus the bi-directional relationship navigation).
- `pytest`: **3 passed, 1 warning in 0.41s**. `ruff check .`: **All checks passed!**.
- Commit landed as `feat(t1): SQLAlchemy 2.0 models + NormalizedResource + init_db lifespan`.
