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

## Turn 4 — Task 2: Synthetic sample data (the offline enabler)

```
Implement data/generate_samples.py that writes data/sample_aws_cur.csv (realistic AWS Cost &
Usage Report columns) and data/sample_azure.csv (Azure billing export columns). Use the
finops-domain skill for the exact column schemas and the orphan definitions. Seed BOTH with a mix
of healthy resources AND deliberately wasteful ones that each rule in SPEC §5 will catch: at least
one unattached EBS volume, one long-stopped EC2, one unassociated Elastic IP, one old orphaned
snapshot (AWS); one unattached managed disk, one long-deallocated VM (Azure). Give the seeded
orphans stable, recognisable IDs and document the expected counts/savings in data/EXPECTED.md.
Run the generator so the files exist. Use python-implementer, then test-author.
Write tests, run them, update prompts.md, commit, report elapsed time.
```

- Loaded the `finops-domain` skill for the AWS CUR / Azure export column schemas (`lineItem/ResourceId`, `lineItem/ProductCode`, `lineItem/UsageType`, `lineItem/UsageAmount`, `lineItem/UnblendedCost`, `product/region`, `bill/BillingPeriodStartDate` on the AWS side; `Date`, `ResourceId`, `MeterCategory`, `ResourceGroup`, `ResourceLocation`, `Quantity`, `CostInBillingCurrency` on the Azure side).
- Wrote `data/generate_samples.py` — fully deterministic (no RNG; `TODAY = date(2026, 5, 30)` is a module constant so age-threshold rules R2/R4/R6 are reproducible). Real CUR/Azure columns are extended with a small set of `resource/*` / `Resource*` state columns (`resource/status`, `resource/attached`, `resource/last_activity_date`, `resource/tags` and Azure analogues) so the parsers can produce a complete `NormalizedResource` from a single CSV per provider, without a separate inventory JSON (SPEC §3 ships only two CSVs). Module-docstring explains the design choice.
- Planted **6 orphans with recognisable IDs**, one per SPEC §5 rule:
  - `vol-0unattachedebs00001` (rule 1) — $12.00
  - `i-0longstoppedec2001`, stopped 80d ago (rule 2) — $25.00
  - `eipalloc-0unassociated001` (rule 3) — $3.65
  - `snap-0orphanedsnap00001`, orphaned 150d ago (rule 4) — $2.50
  - `…/disks/disk-unattached-demo-001` (rule 5) — $5.76
  - `…/virtualMachines/vm-deallocated-demo-001`, deallocated 60d ago (rule 6) — $42.00
  - **Grand total monthly savings: $90.91** (AWS $43.15 + Azure $47.76).
- Planted **6 healthy resources** that must NOT trigger any rule (in-use volume, running EC2, associated EIP, recent snapshot; attached Azure disk, running Azure VM) — same files, distinguishable IDs.
- Wrote `data/EXPECTED.md` — the planted-orphan contract: per-orphan IDs, severities, individual savings, AWS/Azure subtotals, grand total, and a rule→orphan mapping table for downstream detection tests.
- Made `data/` a package (`data/__init__.py`) so tests can `from data.generate_samples import write_samples` without sys.path hacks (data/ is excluded from the wheel via `tool.hatch.build.targets.wheel.packages = ["app"]`). Removed the now-obsolete `data/.gitkeep`.
- Ran the generator: `python data/generate_samples.py` → wrote `data/sample_aws_cur.csv` (8 data rows) and `data/sample_azure.csv` (4 data rows). Committed alongside the generator.
- Wrote `tests/test_samples.py` — 11 deterministic tests using a `tmp_path` fixture so the test never touches the committed CSVs: row counts match EXPECTED.md exactly; every planted orphan ID is present; AWS subtotal == $43.15, Azure subtotal == $47.76, grand total == $90.91 (asserted with `pytest.approx(..., abs=0.01)`); every planted orphan carries the status its rule keys on; every clean row carries a state that no rule triggers on (guards against future false positives).
- `pytest`: **14 passed, 1 warning in 0.53s**. `ruff check .`: **All checks passed!**.
- Commit landed as `feat(t2): synthetic sample data + planted-orphan contract`.
