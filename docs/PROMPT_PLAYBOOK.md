# PROMPT PLAYBOOK — Cloud Cost Optimizer & Remediation Engine
### (with explicit context + skill loading per prompt)

## How to use this
1. Drop `CLAUDE.md`, `SPEC.md`, and the `.claude/skills/` folder into your empty repo first.
2. Open Claude Code in that repo. Paste the prompts **in order, one per turn**.
3. Don't advance until the agent shows green tests + updated `prompts.md` + an elapsed-time line.
   If something's off, tell the agent to fix it (you never edit code).

## Claude Code mechanics (why the 📎 Load blocks work)
- **`CLAUDE.md` auto-loads** at session start — you never need to attach it.
- **Attach context with `@`**: typing `@SPEC.md` (Claude Code tab-completes paths) puts that file in
  the turn's context. Attach the spec section's file + any existing source files the task edits.
- **Skills are matched by their frontmatter `name:`** and triggered by their `description`. Naming a
  skill explicitly ("use the finops-domain skill") makes the trigger reliable. The four skill names
  are exactly: `finops-domain`, `python-implementer`, `test-author`, `code-reviewer`.
- Only `@`-mention a source file once it **exists** (i.e., from the prompt after it's created).

> Section numbers below (SPEC §3/§4/…) assume the SPEC.md you placed at the repo root. If your
> numbering differs, the section *names* in each prompt still point you to the right place.

---

## Prompt 1 — Required challenge kickoff (paste VERBATIM, first message)

📎 **Load with this prompt:** nothing — `CLAUDE.md` auto-loads and sets the operating rules.

> Lead Architect mode: ON. We are building a Python-based, API-first **Cloud Cost Optimizer & Remediation Engine** using a free database and a dashboard.
> Rules:
> - No Manual Edits: You provide all logic and fixes. I will not edit any code.
> - Audit Log: You must maintain a file named prompts.md. After every turn, update that file (or provide the text block) with the prompt I just used.
> - Time-Check: Start a timer. Goal is an MVP in 4-6 hours (Max window: 16h). Report 'Elapsed Time' at the end of every response. Acknowledge and let's start.

*(The brief's mandated opener. The next prompt takes architectural control.)*

---

## Prompt 2 — Task 0: Bootstrap & scaffold

📎 **Load with this prompt:**
- **Context:** `@SPEC.md`
- **Skills:** `python-implementer` (structure & stack conventions)

**PROMPT**
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
**Acceptance:** app imports; `uvicorn app.main:app` boots; `GET /health` → `{"status":"ok"}`; committed.
**Tests required:** `tests/test_health.py` — TestClient GET /health returns 200 and the ok body.

---

## Prompt 3 — Task 1: Domain model & DB layer

📎 **Load with this prompt:**
- **Context:** `@SPEC.md`
- **Skills:** `python-implementer` (SQLAlchemy 2.0 patterns) · `test-author`

**PROMPT**
```
Implement app/models.py (SQLAlchemy 2.0 typed Mapped models: Scan, Resource, Finding per SPEC §4)
and wire init_db() in app/db.py to create tables. Add app/ingestion/normalize.py with the
NormalizedResource dataclass. No parsing/rules yet. Use the python-implementer skill, then the
test-author skill for the tests.
Write tests, run them, update prompts.md, commit, report elapsed time.
```
**Acceptance:** tables create cleanly; a Scan with related Resources/Findings round-trips through a session.
**Tests required:** `tests/test_models.py` — create_all on a tmp/in-memory DB; insert Scan + Resource + Finding; query back and assert relationships + field values.

---

## Prompt 4 — Task 2: Synthetic sample data (the offline enabler)

📎 **Load with this prompt:**
- **Context:** `@SPEC.md`
- **Skills:** `finops-domain` (CUR/Azure column schemas + what each rule catches) · `python-implementer` · `test-author`

**PROMPT**
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
**Acceptance:** running the script produces both CSVs containing the known orphan IDs and realistic cost values; `data/EXPECTED.md` documents planted counts.
**Tests required:** `tests/test_samples.py` — generate to a tmp dir; assert each known orphan ID is present and total row counts are as expected.

---

## Prompt 5 — Task 3: Ingestion / parsers

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/ingestion/normalize.py`
- **Skills:** `finops-domain` (column → NormalizedResource mapping) · `python-implementer` · `test-author`

**PROMPT**
```
Implement app/ingestion/aws_cur.py and app/ingestion/azure.py. Each takes a file path (or bytes)
and returns list[NormalizedResource] (see @app/ingestion/normalize.py) mapping provider-specific
rows to the normalized model (status, attached, monthly_cost, last_activity_date, tags, raw).
Use the finops-domain skill for the correct source columns (cost from UnblendedCost, not usage).
Count and report malformed rows rather than crashing. Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```
**Acceptance:** parsing the sample files yields expected resource counts; the seeded unattached EBS volume parses with `status="available"` and correct cost.
**Tests required:** `tests/test_ingestion.py` — inline tiny CSV fixtures for both providers → assert counts + one mapped field each; one malformed-row case asserting it's counted/skipped, not fatal.

---

## Prompt 6 — Task 4: Rule engine + FIRST rule (vertical slice)

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/ingestion/normalize.py`
- **Skills:** `finops-domain` (rule conditions + savings math) · `python-implementer` · `test-author`

**PROMPT**
```
Implement app/rules/base.py: a Rule protocol, the Finding dataclass, and a REGISTRY the engine
iterates. Implement ONLY the first rule in app/rules/catalog.py: aws_unattached_ebs_volume
(SPEC §5 #1) — registered, not hard-wired into the engine. The engine takes list[NormalizedResource]
-> list[Finding]. Use the finops-domain skill for the exact condition and savings calculation.
Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```
**Acceptance:** the engine returns a high-severity finding for an unattached EBS volume with savings = its monthly_cost; adding a rule requires no engine change.
**Tests required:** `tests/test_rules.py` — positive (unattached volume flagged, severity high, savings correct) + negative (in-use volume NOT flagged).

---

## Prompt 7 — Task 5: Remediation command generator

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/rules/base.py` · `@app/rules/catalog.py`
- **Skills:** `finops-domain` (exact CLI templates + safety rule) · `python-implementer` · `test-author`

**PROMPT**
```
Implement app/remediation.py: given a Finding (+ its resource), return the exact CLI command
string per the finops-domain skill templates / SPEC §5. Map each rule_id to its template. Per the
safety rule, this module imports no cloud SDK and executes nothing; destructive commands are marked
is_destructive. Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```
**Acceptance:** generated commands equal the templates exactly for each finding type; destructive ones flagged.
**Tests required:** `tests/test_remediation.py` — one assertion per rule_id (start with EBS; extend as rules are added) checking exact string equality incl. flags/ids; a source-inspection test asserting no boto3/azure/subprocess import.

---

## Prompt 8 — Task 6: API end-to-end (vertical slice through the API)

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/rules/base.py` · `@app/remediation.py` · `@app/ingestion/normalize.py`
- **Skills:** `python-implementer` (FastAPI/Pydantic patterns) · `test-author`

**PROMPT**
```
Implement app/services.py run_scan(file_bytes, filename, provider) that ingests -> runs the engine
-> generates remediation strings -> persists Scan/Resources/Findings -> returns a ScanSummary.
Wire the API per SPEC §6: POST /scans (multipart), GET /scans, GET /scans/{id},
GET /scans/{id}/findings, GET /scans/{id}/summary. pydantic schemas in app/schemas.py.
Only the EBS rule is active so far — that's fine. Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```
**Acceptance:** POSTing `sample_aws_cur.csv` returns 200 with `total_monthly_savings > 0`; the seeded EBS orphan appears in `/findings` with its command; `/summary` aggregates by type and severity.
**Tests required:** `tests/test_api.py` — full flow: upload sample → assert summary fields, orphan present in findings, aggregation correct.

---

## Prompt 9 — Task 7: Expand the rule catalog

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/rules/base.py` · `@app/rules/catalog.py` · `@app/remediation.py`
- **Skills:** `finops-domain` (the 5 remaining rule defs + templates) · `python-implementer` · `test-author`

**PROMPT**
```
Implement the remaining rules in SPEC §5 (#2-#6): aws_idle_stopped_ec2, aws_unassociated_elastic_ip,
aws_orphaned_snapshot, azure_unattached_managed_disk, azure_deallocated_vm. Each registered in
REGISTRY, each with its remediation template added to app/remediation.py. Use the finops-domain
skill for every condition, savings calc, and command template. For date-threshold rules, inject a
reference 'today' so logic is testable. Use python-implementer, then test-author.
Run tests, update prompts.md, commit, report elapsed time.
```
**Acceptance:** scanning the Azure sample also yields findings; every rule fires on its seeded orphan; total savings sums across all rules.
**Tests required:** extend `tests/test_rules.py` and `tests/test_remediation.py` with a positive + negative + exact-command test per new rule (parametrize).

---

## Prompt 10 — Task 8: Dashboard

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/schemas.py` (so the JS matches the real API shape)
- **Skills:** `python-implementer` (single-file dashboard guidance) · `test-author` (smoke test)

**PROMPT**
```
Implement static/index.html (vanilla JS + Chart.js via CDN) and serve it at GET / per SPEC §7:
file picker + provider select + Scan button (POST /scans), then KPI cards (total monthly savings,
# findings, # high severity), a bar chart of savings by resource_type, and a findings table with a
Copy button per remediation command. Match the response shape in @app/schemas.py. Keep it clean,
no build step. Use python-implementer.
Add a light smoke test (test-author), run all tests, update prompts.md, commit, report elapsed time.
```
**Acceptance:** `GET /` returns the dashboard; after a scan the KPIs, chart, and table populate from the live API; Copy buttons work.
**Tests required:** extend `tests/test_api.py` (or `test_dashboard.py`) — GET / returns 200 and contains the element ids/markers the JS targets.

---

## Prompt 11 — Task 9: README, run docs & the deck

📎 **Load with this prompt:**
- **Context:** `@SPEC.md` · `@app/rules/catalog.py` (for the rule-catalog table)
- **Skills:** `finops-domain` (accurate rule table) — implementation skills not needed for docs

**PROMPT**
```
Write README.md: what it does, architecture diagram (ASCII or mermaid), how to run
(uv sync; python data/generate_samples.py; uvicorn app.main:app; open http://localhost:8000),
how to run tests, the rule catalog table (from @app/rules/catalog.py), and a clear "Cloud cost /
decommission" note: this tool is fully offline and provisions NO cloud resources, so there is
nothing to decommission — it analyses exported billing files and only emits commands. Then generate
the presentation as slides.md (Marp-compatible markdown): problem, architecture, how the rule engine
works, a demo screenshot description, results (sample savings figure), and the vibe-coding workflow
(skills + prompts.md). Update prompts.md, commit, report elapsed time.
```
**Acceptance:** README runs the project from a clean clone; `slides.md` covers the required deck sections.
**Tests required:** none new — but re-run the full suite and confirm green.

---

## Prompt 12 — Task 10: Final review & hardening

📎 **Load with this prompt:**
- **Context:** none needed — the whole repo is already in Claude Code's working tree
- **Skills:** `code-reviewer` (run its checklist across the repo)

**PROMPT**
```
Run the code-reviewer skill across the WHOLE repo. Report PASS/FIX per its checklist, fix every FIX
yourself, ensure ruff is clean and pytest is fully green (paste the summary). Confirm prompts.md
contains every turn, the README decommission note is present, and there are no secrets or network
calls. Tag a v1.0.0 commit. Give me a final 'Elapsed Time' and a one-paragraph summary of what was
built for my submission.
```
**Acceptance:** ruff clean, all tests green, prompts.md complete, no secrets/network, tagged release.
**Tests required:** full suite green; no new tests unless review reveals a gap.

---

### Submission checklist (from the brief)
- [ ] Tagle.ai "Tag" PDF report (do this first, separately — verify it's free).
- [ ] Public GitHub repo on YOUR account, MIT-licensed (this repo).
- [ ] prompts.md — full audit log (auto-built by following this playbook).
- [ ] Deck — `slides.md` (or export to PPTX if you prefer).
- [ ] Decommission confirmation — covered by the README note (no cloud resources were provisioned).

### Skill-loading cheat sheet
| Task | finops-domain | python-implementer | test-author | code-reviewer |
|------|:---:|:---:|:---:|:---:|
| 0 Bootstrap | | ✓ | | |
| 1 Models/DB | | ✓ | ✓ | |
| 2 Sample data | ✓ | ✓ | ✓ | |
| 3 Ingestion | ✓ | ✓ | ✓ | |
| 4 Rule engine | ✓ | ✓ | ✓ | |
| 5 Remediation | ✓ | ✓ | ✓ | |
| 6 API | | ✓ | ✓ | |
| 7 Expand rules | ✓ | ✓ | ✓ | |
| 8 Dashboard | | ✓ | ✓ | |
| 9 Docs/deck | ✓ | | | |
| 10 Final review | | | | ✓ |
