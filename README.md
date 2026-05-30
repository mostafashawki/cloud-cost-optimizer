# Cloud Cost Optimizer & Remediation Engine

Offline, **API-first** Python service that ingests *exported* AWS / Azure
billing CSVs, flags orphaned and idle resources with a small rule engine,
estimates monthly waste in USD, and emits the exact CLI command needed to
decommission each one. A single-file dashboard at `/` lets a human upload a
file and read the verdict.

The tool never authenticates to a cloud account. It calls **no** SDKs, makes
**no** outbound network requests, and executes **none** of the commands it
generates. That's by design — see [§ Cloud decommission note](#-cloud-decommission-note).

---

## What it does

| Capability | Where it lives |
|---|---|
| Parse AWS CUR & Azure billing exports → `NormalizedResource` | `app/ingestion/{aws_cur,azure}.py` |
| Run pluggable detection rules → `Finding` | `app/rules/{base,catalog}.py` |
| Map a finding to a verbatim decommission CLI command | `app/remediation.py` |
| Persist scans / resources / findings in SQLite | `app/models.py`, `app/db.py` |
| Expose the JSON API (`/scans`, `/findings`, `/summary`) | `app/api/scans.py` |
| Serve a one-file dashboard at `/` | `static/index.html` |

Run a scan against the bundled sample data and you get **6 findings totalling
$90.91 / month** — every planted orphan is detailed in
[`data/EXPECTED.md`](data/EXPECTED.md).

---

## Architecture

```mermaid
flowchart LR
  CSV["AWS CUR CSV / Azure export CSV"] --> Parsers["app/ingestion/&#123;aws_cur,azure&#125;.py"]
  Parsers -->|list[NormalizedResource]| Engine["app/rules/base.run_engine"]
  Catalog["app/rules/catalog.py<br/>(R1..R6, registered in REGISTRY)"] -.-> Engine
  Engine -->|list[Finding]| Remediation["app/remediation.generate"]
  Remediation -->|command string| Services["app/services.run_scan"]
  Parsers --> Services
  Services -->|persist| DB["SQLite via SQLAlchemy 2.0<br/>Scan / Resource / Finding"]
  Services -->|ScanSummary| API["FastAPI routes<br/>POST /scans, GET /scans/&#123;id&#125;/{findings,summary}"]
  API --> Dash["static/index.html<br/>(KPIs + Chart.js bar + Copy button)"]
  API --> JSON["Any JSON client"]
```

ASCII version for terminals without mermaid:

```
exported CSV ──► parsers ──► list[NormalizedResource]
                                   │
                                   ▼
                       run_engine ──► list[Finding]
                          ▲                 │
                          │                 ▼
                       REGISTRY     remediation.generate
                       (R1..R6)            │
                                           ▼
                                services.run_scan ──► SQLite (Scan/Resource/Finding)
                                           │
                                           ▼
                                  FastAPI JSON ──► dashboard at GET /
```

---

## How to run

> **Prereq:** Python 3.11+. Either `uv` (fast) or plain `pip` + `venv` works.

### With `uv` (preferred)

```bash
uv sync                                 # install runtime + dev deps from pyproject.toml
uv run python data/generate_samples.py  # write the sample CSVs (one-time)
uv run uvicorn app.main:app             # serve on http://127.0.0.1:8000
# open http://127.0.0.1:8000 in a browser, choose data/sample_aws_cur.csv, click Scan
```

### Without `uv` (pip fallback)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python data/generate_samples.py
uvicorn app.main:app
# open http://127.0.0.1:8000
```

`uvicorn app.main:app --reload` is the iteration loop while editing code.

### Sanity check

```bash
curl http://127.0.0.1:8000/health
# → {"status":"ok"}

curl -X POST http://127.0.0.1:8000/scans \
  -F "file=@data/sample_aws_cur.csv" -F "provider=aws"
# → {"scan_id":1,"resource_count":8,"finding_count":4,"total_monthly_savings":43.15,...}
```

### Tests

```bash
pytest -q              # whole suite; ~0.5s on a laptop
ruff check .           # lint
```

The suite is **73 tests, fully offline, no network, no real cloud**. Each
task in [`docs/PLAN.md`](docs/PLAN.md) lists the tests it added.

---

## Rule catalog

Implemented in [`app/rules/catalog.py`](app/rules/catalog.py); each rule is a
small frozen dataclass registered into `REGISTRY` so adding a new rule is a
one-line `register(...)` call (the engine never changes).

| # | rule_id | Provider / type / condition | Severity | Savings | Remediation command |
|---|---|---|---|---|---|
| 1 | `aws_unattached_ebs_volume` | `aws` / `ebs_volume` / `status=available` | **high** | monthly cost | `aws ec2 delete-volume --volume-id {rid} --region {region}` |
| 2 | `aws_idle_stopped_ec2` | `aws` / `ec2_instance` / `status=stopped` & last activity > **30d** | medium | monthly cost | `aws ec2 terminate-instances --instance-ids {rid} --region {region}` *(destructive)* |
| 3 | `aws_unassociated_elastic_ip` | `aws` / `elastic_ip` / `status=unassociated` | **high** | monthly cost | `aws ec2 release-address --allocation-id {rid} --region {region}` |
| 4 | `aws_orphaned_snapshot` | `aws` / `ebs_snapshot` / `attached=false` & age > **90d** | low | monthly cost | `aws ec2 delete-snapshot --snapshot-id {rid} --region {region}` |
| 5 | `azure_unattached_managed_disk` | `azure` / `managed_disk` / `status=unattached` | **high** | monthly cost | `az disk delete --ids {rid} --yes` |
| 6 | `azure_deallocated_vm` | `azure` / `virtual_machine` / `status=deallocated` & last activity > **30d** | medium | monthly cost | `az vm delete --ids {rid} --yes` *(destructive)* |

`{rid}` is the resource id (the AWS volume / instance / allocation id or the
full Azure ARM resource id). Destructive commands delete potentially
restartable compute and are flagged `is_destructive=True` by
`app/remediation.py`; the other four delete already-orphaned objects.

---

## API quick reference

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{"status":"ok"}` |
| GET | `/` | — | dashboard HTML |
| POST | `/scans` | multipart: `file`, `provider` (`aws`/`azure`) | `ScanSummary` |
| GET | `/scans` | — | `[ScanSummary]` (newest first) |
| GET | `/scans/{id}` | — | `ScanSummary` |
| GET | `/scans/{id}/findings` | — | `[FindingOut]` |
| GET | `/scans/{id}/summary` | — | `ScanAggregations` |

Schemas (Pydantic v2) live in [`app/schemas.py`](app/schemas.py); the
dashboard JS in `static/index.html` matches those field names verbatim.

---

## Project layout

```
cloud-cost-optimizer/
├── app/                  # application code
│   ├── api/scans.py      # FastAPI router (SPEC §6)
│   ├── db.py             # SQLite engine, Session, init_db()
│   ├── ingestion/        # provider-specific CSV parsers
│   ├── main.py           # app factory + GET /health + GET /
│   ├── models.py         # SQLAlchemy 2.0 typed Mapped models
│   ├── remediation.py    # finding -> command string (no cloud SDK!)
│   ├── rules/            # detection rule engine + catalog
│   ├── schemas.py        # Pydantic v2 request/response models
│   └── services.py       # run_scan orchestration
├── data/
│   ├── EXPECTED.md       # the planted-orphan contract
│   ├── generate_samples.py
│   ├── sample_aws_cur.csv
│   └── sample_azure.csv
├── static/index.html     # single-file dashboard (Chart.js via CDN)
├── tests/                # one test module per concern (73 tests)
├── docs/                 # SPEC.md, PLAN.md, PROMPT_PLAYBOOK.md
├── CLAUDE.md             # operating rules for the AI engineer
├── prompts.md            # full prompt audit log (every turn)
├── pyproject.toml
└── README.md             # this file
```

---

## Cloud decommission note

**This tool provisions no cloud resources.** It is fully offline: it reads
*exported* billing files and emits *command strings*. It never
authenticates to AWS or Azure, never runs `boto3` or `azure-sdk`, never opens
a network connection, and never executes any command it produces. The
remediation module is asserted SDK-free via an AST-walking source-inspection
test in `tests/test_remediation.py`.

Consequently, **there is nothing to decommission at the end of this
project** — no S3 buckets, no IAM roles, no resource groups, no shut-down
checklist. The artifact is source code + a local SQLite file. Delete the
repo and you're done.

This is a deliberate design choice. The brief asked for cost optimisation
and remediation; doing that defensively (commands only, operator runs them)
is safer than executing destructive cloud operations from a build tool.

---

## Future work

Tracked in `docs/PLAN.md` T9 (Stretch) and noted here so they don't leak
into the MVP:

- Dockerfile + compose for one-command run.
- Month-over-month cost trend chart on `/scans/{id}/summary`.
- Cost-allocation-by-tag aggregation in `/summary`.
- Multi-scan diff (was this volume orphaned last month too?).
- Authenticated upload for shared deployments (right now it's single-user offline).

---

## License

MIT — see `LICENSE` (or the `license` field in `pyproject.toml` if one isn't
checked in yet).
