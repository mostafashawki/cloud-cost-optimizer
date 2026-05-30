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

## Turn 5 — Task 3: Ingestion / parsers

```
Implement app/ingestion/aws_cur.py and app/ingestion/azure.py. Each takes a file path (or bytes)
and returns list[NormalizedResource] (see @app/ingestion/normalize.py) mapping provider-specific
rows to the normalized model (status, attached, monthly_cost, last_activity_date, tags, raw).
Use the finops-domain skill for the correct source columns (cost from UnblendedCost, not usage).
Count and report malformed rows rather than crashing. Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```

- Added `app/ingestion/_parsing.py` — shared parser building blocks: `ParseResult` dataclass (`resources`, `malformed_count`, `errors`), `open_text(source)` that accepts `str | bytes | Path | IO[str]` (so the same parser entry-point serves CLI users, FastAPI `UploadFile` bytes, and inline-string tests), `parse_bool` with a strict truthy-token set, `parse_optional_date` (empty → None, malformed → ValueError so the row is counted), `parse_kv_pairs(value, *, kv_sep)` (one helper for both `k=v;k=v` AWS and `k:v;k:v` Azure tag formats), and a `check_required_columns(...)` precondition that returns a schema-error `ParseResult` instead of raising.
- Implemented `app/ingestion/aws_cur.py` — `parse(source) -> ParseResult` mapping `lineItem/ResourceId` → `resource_id`, `lineItem/UnblendedCost` → `monthly_cost` (per finops-domain skill: **cost is UnblendedCost, never UsageAmount** — using usage as cost is the classic CUR bug), `product/region` → `region`, plus the extended `resource/type|status|attached|last_activity_date|tags` columns to the corresponding `NormalizedResource` fields. Full source row is preserved in `raw`. Bad rows (empty resource id, unparseable cost, malformed date) are caught with `except (ValueError, KeyError)`, counted, and logged via `logging` — never raised. Error messages use spreadsheet-style 1-based row numbers (header is row 1, data starts at row 2).
- Implemented `app/ingestion/azure.py` — mirror of the AWS parser but reading `ResourceId`, `CostInBillingCurrency`, `ResourceLocation`, and the extended `ResourceType|ResourceStatus|Attached|LastActivityDate|Tags` columns. Tags use `:` as the key/value separator (Azure portal convention). `provider="azure"` is hard-coded.
- Wrote `tests/test_ingestion.py` — 13 tests covering everything the playbook required *and* the T3 acceptance criteria:
  - Inline tiny CSV fixtures both providers → counts + per-field mapping assertions (provider, type, region, status, monthly_cost, attached, last_activity_date, tags).
  - Both `_skips_malformed_row_and_keeps_going` tests insert a deliberately bad row between two valid rows; result asserts `malformed_count == 1`, an error mentioning `row 3`, and the two valid resources still surface (i.e. **bad data is not fatal**).
  - Acceptance: `aws_cur.parse(data/sample_aws_cur.csv)` returns 8 resources, `azure.parse(data/sample_azure.csv)` returns 4, `vol-0unattachedebs00001` parses with `status="available"` and `monthly_cost == $12.00`, `disk-unattached-demo-001` parses with `status="unattached"` and `monthly_cost == $5.76`.
  - Edge cases: empty file → schema error not crash; missing required columns → schema error; bytes / Path / pre-opened stream all accepted; date column empty → None; tags `k=v;k=v` and `k:v;k:v` parse to identical dict shapes.
- First run had **2 failures** in the malformed-row tests — I'd accidentally passed the CSV as a `str` to `parse(...)`, which `open_text` interprets as a file path. Fixed the tests to pass `.encode("utf-8")` (one-line change per test, no parser change needed). Second run: green.
- `pytest`: **25 passed, 1 warning in 0.48s**. `ruff check .`: **All checks passed!**.
- Commit landed as `feat(t3): AWS CUR + Azure CSV parsers with malformed-row tolerance`.

## Turn 6 — Task 4: Rule engine + FIRST rule (vertical slice)

```
Implement app/rules/base.py: a Rule protocol, the Finding dataclass, and a REGISTRY the engine
iterates. Implement ONLY the first rule in app/rules/catalog.py: aws_unattached_ebs_volume
(SPEC §5 #1) — registered, not hard-wired into the engine. The engine takes list[NormalizedResource]
-> list[Finding]. Use the finops-domain skill for the exact condition and savings calculation.
Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```

- Implemented `app/rules/base.py` — engine primitives:
  - `Severity = Literal["low","medium","high"]`.
  - `Finding` frozen slotted dataclass (in-memory, distinct from the ORM `models.Finding`; services.run_scan in T6 will map between them). Fields: `rule_id`, `resource_id`, `resource_type`, `provider`, `region`, `title`, `reason`, `severity`, `estimated_monthly_savings`, `remediation_command` (default `""`, populated in T5).
  - `Rule` `@runtime_checkable Protocol` requiring `rule_id`, `title`, `severity` attributes plus `__call__(resource) -> Finding | None`.
  - `REGISTRY: dict[str, Rule]` keyed on `rule_id` (so duplicate registration raises `ValueError` instead of silently shadowing).
  - `register(rule)` decorator-style helper.
  - `run_engine(resources)` iterates `REGISTRY.values()` once per resource (resource-outer / rule-inner so all findings for resource A precede any for resource B — matches what `services.run_scan` will want when attaching findings to the persisted resource row).
- Implemented **only** SPEC §5 #1 in `app/rules/catalog.py` — `AwsUnattachedEbsVolume` (frozen dataclass instance, registered via a single `register(AwsUnattachedEbsVolume())` call). Condition: `provider == "aws" and resource_type == "ebs_volume" and status == "available"`. Severity `high`. Savings = `round(resource.monthly_cost, 2)` per python-implementer's "round at the boundary" guidance. Reason string includes the resource id and the trigger status for human-readable findings.
- Wrote `tests/test_rules.py` — **9 tests** covering:
  - Engine/registry contract: rule is registered, satisfies the `Rule` Protocol via `isinstance` (works because the Protocol is `@runtime_checkable`); `run_engine([])` returns `[]`; **engine-source-inspection test** uses `inspect.getsource(rules_base)` to assert the literal strings `"aws_unattached_ebs_volume"` and `"azure_unattached_managed_disk"` are absent from `base.py` — direct evidence of the "adding a rule requires no engine change" acceptance criterion.
  - Positive: unattached EBS volume → flagged with `severity=="high"`, savings == `$12.00`, every field on the `Finding` populated correctly, `remediation_command == ""` (T5 territory).
  - Boundary: savings of `9.123456` round to `9.12`.
  - Negative cases: in-use volume not flagged; an Azure-provider resource with `resource_type="ebs_volume"` not flagged (tests the provider gate); an EC2 instance with `status="available"` not flagged (tests the resource_type gate).
  - Mixed input: only the one orphan is reported among `[healthy, orphan, healthy]`.
- Ruff initially flagged one import-order issue; `ruff check --fix .` resolved it (single-file isort touch in the test).
- `pytest`: **34 passed, 1 warning in 0.50s**. `ruff check .`: **All checks passed!**.
- Commit landed as `feat(t4): rule engine + aws_unattached_ebs_volume (first vertical-slice rule)`.

## Turn 7 — Task 5: Remediation command generator

```
Implement app/remediation.py: given a Finding (+ its resource), return the exact CLI command
string per the finops-domain skill templates / SPEC §5. Map each rule_id to its template. Per the
safety rule, this module imports no cloud SDK and executes nothing; destructive commands are marked
is_destructive. Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```

- Implemented `app/remediation.py` carrying the full SPEC §5 template table up front (all six rules, not just EBS) so T7's rule additions don't need to touch this module:
  - `_TEMPLATES: dict[str, _Template]` mapping `rule_id` → (`template`, `is_destructive`). Format placeholders are `{rid}` (resource id) and `{region}`; Azure templates omit `--region` and silently ignore the extra `region=...` kwarg.
  - `RemediationCommand(command, is_destructive)` frozen dataclass returned by `generate(finding)`. Destructive-flag policy: deletes of potentially-restartable compute (`terminate-instances`, `vm delete`) are marked `True`; deletes of already-orphaned objects (unattached vol/disk, unassociated EIP, orphaned snapshot) are `False` — they cannot disrupt any live workload by definition.
  - Unknown `rule_id` → `KeyError("no remediation template for rule_id=…")` to surface programmer errors loudly.
  - Public helper `supported_rule_ids()` returns the set of templated rule_ids (useful for the parity test below and for catalog/template consistency in T7).
  - **Safety contract** spelled out in the module docstring: no `boto3`, no `botocore`, no `azure-*`, no `subprocess`, no `os.system`.
- Wrote `tests/test_remediation.py` — **9 test cases / 8 functions**:
  - **Parametrized** "exact template" test runs 6 times (one per `rule_id`), each asserting `result.command == expected_command` byte-for-byte and `result.is_destructive` matches the expected flag (True for `aws_idle_stopped_ec2` + `azure_deallocated_vm`; False for the other four).
  - `KeyError` raised with the rule_id in the message for an unknown finding.
  - **Parity** test: `{case.id for case in REMEDIATION_CASES} == supported_rule_ids()` — so the suite stays in lock-step with the template dict; a future rule added to `_TEMPLATES` but forgotten in tests would fail this assertion immediately.
  - **Safety / source-inspection** test: parses `app/remediation.py` with `ast.parse(...)`, walks `ast.Import` + `ast.ImportFrom` nodes, and asserts none has a top-level module name in `{"boto3", "botocore", "azure", "subprocess", "os.system"}`. AST parsing instead of substring grep means the forbidden words can still appear in the module's *docstring* (where the safety contract is documented) without flunking the test — only actual import statements fail it.
- `pytest`: **43 passed, 1 warning in 0.51s**. `ruff check .`: **All checks passed!**.
- Commit landed as `feat(t5): remediation command generator + safety/source-inspection test`.
