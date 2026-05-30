# SPEC.md — Cloud Cost Optimizer & Remediation Engine

## 1. Vision
A Python, API-first tool that ingests **exported** AWS/Azure billing data (CSV/JSON), detects
**orphaned / idle** resources via a rule engine, estimates monthly waste in USD, and generates
the exact CLI command to decommission each one. A dashboard visualises potential savings.
The tool is fully offline — it never connects to a cloud account. (This also means there are
**no cloud resources to decommission** at the end: a deliberate design choice, stated in the README.)

## 2. Tech
Python 3.11+, FastAPI + uvicorn, SQLAlchemy 2.0 over SQLite, pydantic v2, pytest, ruff, uv.

## 3. Package layout
```
cloud-cost-optimizer/
├── app/
│   ├── main.py            # FastAPI app + routes (thin)
│   ├── db.py              # engine, Session, init_db()
│   ├── models.py          # ORM: Scan, Resource, Finding
│   ├── schemas.py         # pydantic request/response models
│   ├── services.py        # run_scan(): ingest -> detect -> persist
│   ├── remediation.py     # finding -> CLI command string
│   ├── ingestion/
│   │   ├── normalize.py   # NormalizedResource dataclass
│   │   ├── aws_cur.py     # AWS Cost & Usage Report (CSV) parser
│   │   └── azure.py       # Azure billing export (CSV) parser
│   └── rules/
│       ├── base.py        # Rule protocol, Finding dataclass, REGISTRY
│       └── catalog.py     # concrete rules
├── static/index.html      # dashboard (vanilla JS + Chart.js via CDN)
├── data/
│   ├── generate_samples.py
│   ├── sample_aws_cur.csv
│   └── sample_azure.csv
├── tests/                 # one test module per concern
├── CLAUDE.md  SPEC.md  prompts.md  README.md  pyproject.toml  .gitignore
```

## 4. Normalized data model
**NormalizedResource** (internal, produced by parsers):
`provider` (aws|azure), `resource_id`, `resource_type`, `region`, `status`,
`monthly_cost` (float USD), `attached` (bool), `last_activity_date` (date|None),
`tags` (dict), `raw` (dict).

**ORM tables**
- `scans`: id, created_at, source_filename, provider, resource_count, finding_count, total_monthly_savings
- `resources`: id, scan_id(fk), provider, resource_id, resource_type, region, status, monthly_cost, attached, last_activity_date, tags(json), raw(json)
- `findings`: id, scan_id(fk), resource_pk(fk), rule_id, title, reason, severity(low|medium|high), estimated_monthly_savings, remediation_command, created_at

## 5. Rule catalog (rule_id → trigger → severity → savings → command template)
1. `aws_unattached_ebs_volume` — aws / ebs_volume / status=available → **high** → full monthly_cost →
   `aws ec2 delete-volume --volume-id {rid} --region {region}`
2. `aws_idle_stopped_ec2` — aws / ec2_instance / status=stopped & last_activity > 30d → **medium** → monthly_cost →
   `aws ec2 terminate-instances --instance-ids {rid} --region {region}`
3. `aws_unassociated_elastic_ip` — aws / elastic_ip / status=unassociated → **high** → monthly_cost →
   `aws ec2 release-address --allocation-id {rid} --region {region}`
4. `aws_orphaned_snapshot` — aws / ebs_snapshot / attached=false & last_activity > 90d → **low** → monthly_cost →
   `aws ec2 delete-snapshot --snapshot-id {rid} --region {region}`
5. `azure_unattached_managed_disk` — azure / managed_disk / status=unattached → **high** → monthly_cost →
   `az disk delete --ids {rid} --yes`
6. `azure_deallocated_vm` — azure / virtual_machine / status=deallocated & last_activity > 30d → **medium** → monthly_cost →
   `az vm delete --ids {rid} --yes`

Each rule is a callable registered in `REGISTRY`. Adding a rule must not require touching the engine.

## 6. API contract
- `GET  /health` → `{"status":"ok"}`
- `POST /scans` (multipart: `file`, `provider`) → ingest+detect+persist → `ScanSummary`
- `GET  /scans` → `[ScanSummary]`
- `GET  /scans/{id}` → `ScanSummary`
- `GET  /scans/{id}/findings` → `[Finding]` (incl. `remediation_command`)
- `GET  /scans/{id}/summary` → `{total_monthly_savings, by_resource_type:{...}, by_severity:{...}}`
- `GET  /` → serves `static/index.html`

`ScanSummary` = {scan_id, source_filename, provider, resource_count, finding_count, total_monthly_savings, created_at}

## 7. Dashboard
Single page: file picker + provider select + "Scan" button → POST /scans; then render
KPI cards (total monthly savings, # findings, # high-severity), a bar chart of savings by
resource_type (Chart.js), and a findings table with a **Copy** button per remediation command.

## 8. Global acceptance criteria
- `uvicorn app.main:app` boots; `/health` returns ok.
- `python data/generate_samples.py` writes both sample files containing known orphans.
- Scanning `sample_aws_cur.csv` yields findings whose `total_monthly_savings > 0` and includes
  the seeded unattached EBS volume.
- Every rule has at least one positive and one negative test.
- Remediation commands match the templates above exactly.
- `pytest` is green; ruff is clean. README explains run steps and the "no cloud to decommission" note.
