# PLAN.md — Ordered Task Breakdown

Execute top to bottom. Each task: implement against `SPEC.md`, write the **Required tests**, make
them pass, run `ruff`, then run the `code-reviewer` skill. A task is not "done" until all four hold.
"Required tests" lists test function names the suite must contain.

---

## T0 — Bootstrap
**Objective:** Runnable skeleton + tooling + CI.
**In:** repo layout from CLAUDE.md, `pyproject.toml` (pinned deps), `ruff` config, `.gitignore`
(`data/`, `__pycache__`, `.venv`), app factory, `GET /health`, GitHub Actions workflow running
`ruff check .` + `pytest`, initialise `prompts.md`.
**Out:** any domain logic.
**Acceptance:** `uvicorn app.main:app` boots; `/health` → `{"status":"ok"}`; CI workflow present.
**Required tests:** `test_health_returns_ok`.

## T1 — Persistence layer
**Objective:** SQLAlchemy 2.0 models + session + table creation.
**In:** `app/db.py` (engine, `SessionLocal`, `create_all`), `app/models.py` (the four tables in SPEC §3).
**Acceptance:** tables created on startup; a row can be inserted and read back per model.
**Required tests:** `test_create_all_creates_tables`, `test_insert_and_read_finding`.

## T2 — Sample data generator
**Objective:** Reproducible inputs with a known, documented set of planted orphans.
**In:** `scripts/generate_sample_data.py` (seeded RNG) → `sample/aws_cur.csv`, `sample/aws_inventory.json`,
`sample/azure_cost.csv`, `sample/azure_inventory.json`. Document planted counts in a module docstring
AND a `sample/EXPECTED.md` (e.g. 3 unattached volumes, 2 idle EIPs, 1 long-stopped instance,
2 orphaned snapshots, plus clean resources that must NOT be flagged).
**Acceptance:** running the script is idempotent; outputs match documented schemas and planted counts.
**Required tests:** `test_sample_has_expected_planted_counts`, `test_sample_files_match_schema`,
`test_clean_resources_present_and_unflaggable`.

## T3 — Ingestion
**Objective:** Parse + validate + persist billing and inventory for both providers.
**In:** `app/ingest.py` parsers, `app/api/ingest.py` endpoints (`POST /ingest/billing`,
`POST /ingest/inventory`), Pydantic validation.
**Acceptance:** valid files persist with correct row/resource counts; malformed files → 400/422 with
a clear message, never 500; unknown provider rejected.
**Required tests:** `test_ingest_aws_billing_persists_rows`, `test_ingest_inventory_persists_resources`,
`test_ingest_rejects_malformed_csv`, `test_ingest_rejects_unknown_provider`.

## T4 — Detection engine
**Objective:** Rules R1–R6 as deterministic pure functions in `app/detect.py`.
**In:** one function per rule + an orchestrator that joins billing+inventory and returns findings.
**Acceptance:** on sample data each rule flags exactly its planted orphans, savings match expected
values, and clean resources produce zero findings.
**Required tests:** `test_r1_flags_only_unattached_volumes`, `test_r2_flags_only_unassociated_eips`,
`test_r3_flags_long_stopped_instances`, `test_r4_flags_orphaned_snapshots`,
`test_r5_flags_idle_billed_lines`, `test_detection_total_savings_matches_expected`,
`test_no_findings_for_clean_resources`.

## T5 — Remediation generator
**Objective:** Map findings → CLI commands + assemble safe `remediation.sh`.
**In:** `app/remediate.py` (templates per SPEC §5, severity, savings, script builder with banner +
destructive gating).
**Acceptance:** each finding gets a correct command; destructive commands commented unless
`confirm=true`; module performs no execution.
**Required tests:** `test_command_for_unattached_volume_is_correct`,
`test_destructive_commands_commented_without_confirm`,
`test_destructive_commands_active_with_confirm`,
`test_remediate_module_imports_no_cloud_sdk_or_subprocess` (assert by source inspection).

## T6 — Analysis orchestration + APIs
**Objective:** Wire detection into the API surface.
**In:** `POST /analyze`, `GET /findings` (+ filters), `GET /findings/{id}`, `GET /summary`,
`GET /remediation/script`.
**Acceptance:** end-to-end via `TestClient` on sample data returns the known planted totals; filters
work; `/summary` aggregates correctly.
**Required tests:** `test_end_to_end_analyze_returns_expected_totals`,
`test_findings_filter_by_rule_and_min_savings`, `test_summary_aggregates_by_type`,
`test_remediation_script_endpoint_returns_shell`.

## T7 — Dashboard
**Objective:** Single-page dashboard at `/` consuming the API.
**In:** `app/static/index.html` (KPI cards, savings-by-type bar chart via Chart.js, findings table +
copy-command button, empty state).
**Acceptance:** `GET /` returns HTML; charts/table populate from the JSON API after analyze.
**Required tests:** `test_dashboard_route_returns_html`, `test_dashboard_references_summary_endpoint`.

## T8 — Hardening + docs
**Objective:** Production-of-an-MVP polish.
**In:** consistent error handling + empty states, `README.md` (setup, one-line demo via a `make demo`
or shell snippet, the decommission statement), `.env.example`, full e2e test, ruff clean.
**Acceptance:** Global acceptance criteria 1–6 in SPEC §9 all hold from a clean checkout.
**Required tests:** `test_full_pipeline_clean_checkout` (ingest→analyze→summary asserts planted totals).

## T9 — Stretch (only if time remains)
Pick ONE: Dockerfile + compose for one-command run; OR month-over-month cost trend in `/summary` +
a line chart; OR cost-allocation-by-tag report. Must keep all prior tests green. Skip without penalty
if the 4–6h MVP window is closing.

---

### Definition of Done (per task)
`Required tests` present & green · `ruff check .` clean · `code-reviewer` skill run & findings
resolved · `prompts.md` updated · Elapsed Time reported.
