---
marp: true
theme: default
paginate: true
size: 16:9
title: Cloud Cost Optimizer & Remediation Engine
---

<!-- _class: lead -->

# Cloud Cost Optimizer & Remediation Engine

**Offline analyzer for AWS / Azure billing exports** — flags orphaned and
idle resources, emits the exact decommission CLI command, never touches a
cloud account.

Built in **~1.5 hours** with Claude Code as the engineer, using a structured
prompt playbook, four domain skills, and a verbatim audit log of every turn.

<sub>Mostafa Shawki · 2026-05-30</sub>

---

## 1. The problem

- Cloud accounts accumulate **forgotten** resources: detached EBS volumes
  that no one will ever attach again, EC2 boxes "stopped for now" since
  Q3 last year, unassociated Elastic IPs still billing $3.65/mo each.
- Manual audits are tedious and don't repeat — the waste re-accumulates.
- Most existing tools require **read-write IAM permissions** in production
  accounts, which security teams reasonably don't want to hand out for an
  experimental dashboard.

**Goal:** detect waste from *exported* billing data, produce a precise
list of orphans + the exact CLI command to kill each one, ship a humans-
in-the-loop dashboard, **without ever authenticating to the cloud**.

---

## 2. Architecture

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
                                services.run_scan ──► SQLite
                                           │
                                           ▼
                                  FastAPI JSON ──► dashboard
```

- **FastAPI + uvicorn** for the API.
- **SQLAlchemy 2.0 typed Mapped** models over SQLite (one local file).
- **Pydantic v2** schemas at every boundary.
- **No `boto3`, no `azure-sdk`, no `subprocess`** — verified by an AST-walking test.

---

## 3. How the rule engine works

Rules are small frozen dataclasses with one method:

```python
@dataclass(frozen=True, slots=True)
class AwsUnattachedEbsVolume:
    rule_id = "aws_unattached_ebs_volume"
    title   = "Unattached EBS volume"
    severity = "high"

    def __call__(self, resource, *, today=None):
        if (resource.provider == "aws"
            and resource.resource_type == "ebs_volume"
            and resource.status == "available"):
            return Finding(..., estimated_monthly_savings=round(resource.monthly_cost, 2))
        return None
```

- Registered with one `register(AwsUnattachedEbsVolume())` call.
- The engine iterates `REGISTRY` and **never references a rule_id**
  (asserted by reading the engine source and grepping). Adding a rule =
  one new class + one register line. No engine edit.
- Date-threshold rules accept an injected `today=` so unit tests are
  hermetic regardless of when the suite runs.

---

## 4. Detection rules implemented (SPEC §5)

| # | rule_id | Severity | When it fires |
|---|---|---|---|
| 1 | aws_unattached_ebs_volume | high | volume `status=available` |
| 2 | aws_idle_stopped_ec2 | medium | EC2 stopped > 30d |
| 3 | aws_unassociated_elastic_ip | high | EIP unassociated |
| 4 | aws_orphaned_snapshot | low | snapshot, no parent, > 90d |
| 5 | azure_unattached_managed_disk | high | disk `status=unattached` |
| 6 | azure_deallocated_vm | medium | VM deallocated > 30d |

Each rule has a matching CLI template in `app/remediation.py`.
Destructive commands (terminate-instances, vm delete) are flagged
`is_destructive=True`; the operator decides whether to run them.

---

## 5. Dashboard

```
┌──────────────────────────────────────────────────────────────┐
│  Cloud Cost Optimizer & Remediation Engine                   │
│  Offline analyzer for AWS / Azure billing exports.           │
├──────────────────────────────────────────────────────────────┤
│  [📄 Choose file ▾]  [Provider: AWS ▾]   [    Scan    ]     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Total saving │  │ # Findings   │  │ # High sev   │       │
│  │   $43.15     │  │      4       │  │      2       │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│                                                              │
│  Monthly savings by resource type:                           │
│    ec2_instance ████████████████████████████   $25.00       │
│    ebs_volume   ███████████████                  $12.00     │
│    elastic_ip   ████                              $3.65     │
│    ebs_snapshot ███                               $2.50     │
│                                                              │
│  Findings (4)                                                │
│  ┌──────────────────────────────┬──────────┬──────┬───────┐ │
│  │ Rule / resource              │ Severity │ $/mo │  Copy │ │
│  ├──────────────────────────────┼──────────┼──────┼───────┤ │
│  │ aws_unattached_ebs_volume    │   HIGH   │$12.00│ [Copy]│ │
│  │ vol-0unattachedebs00001      │          │      │       │ │
│  │   aws ec2 delete-volume ...                            │ │
│  └──────────────────────────────┴──────────┴──────┴───────┘ │
└──────────────────────────────────────────────────────────────┘
```

Single-file `static/index.html`. Vanilla JS, Chart.js via CDN, no build step.

---

## 6. Results on the sample data

`python data/generate_samples.py` writes two CSVs with **6 deliberately
planted orphans + 6 healthy resources**. All numbers below are asserted
verbatim in `tests/`.

| Planted orphan | Rule | $/mo |
|---|---|---:|
| `vol-0unattachedebs00001` | aws_unattached_ebs_volume | 12.00 |
| `i-0longstoppedec2001` (80d stopped) | aws_idle_stopped_ec2 | 25.00 |
| `eipalloc-0unassociated001` | aws_unassociated_elastic_ip | 3.65 |
| `snap-0orphanedsnap00001` (150d old) | aws_orphaned_snapshot | 2.50 |
| `…/disk-unattached-demo-001` | azure_unattached_managed_disk | 5.76 |
| `…/vm-deallocated-demo-001` (60d) | azure_deallocated_vm | 42.00 |
| | **Total** | **$90.91** |

The 6 healthy resources in the same files are **not** flagged — guards
against future false positives.

---

## 7. The vibe-coding workflow

**Skills** (in `.claude/skills/`) — each is a small Markdown file the AI
loads on demand:

| Skill | Used when |
|---|---|
| `finops-domain` | CUR/Azure column schemas + the SPEC §5 rules |
| `python-implementer` | FastAPI / SQLAlchemy 2.0 / Pydantic v2 patterns |
| `test-author` | pytest conventions, fixture style, what to assert |
| `code-reviewer` | end-of-task self-review against the spec |

**Process per task:**

1. Paste the next prompt from `docs/PROMPT_PLAYBOOK.md`.
2. AI implements → writes tests → runs them.
3. AI updates `prompts.md` with the verbatim prompt + a summary of changes.
4. AI commits with a conventional message (`feat(t6):` …) and posts an
   elapsed-time line.
5. If anything's red, **fix it** — the human never edits code.

---

## 8. The audit log

`prompts.md` contains **every prompt** I sent and a 3–8 bullet summary of
what the AI did on each turn — generated by the AI itself, then committed
alongside the code. Each turn ends with `⏱️ Elapsed Time: …`.

That makes the workflow **reproducible**: someone re-running the playbook
in order should get the same 6 rules, the same $90.91, the same 73 tests.

---

## 9. Numbers from this build

- **9 conventional commits** (`feat:` t0 → t8 + docs t9).
- **73 tests, fully offline, no network**.
- **0 cloud resources provisioned** — the tool is offline by design;
  there is nothing to decommission.
- **MVP elapsed time ≈ 1h 30m** (target 4–6h, hard cap 16h).

---

<!-- _class: lead -->

# Thank you

Repo: `cloud-cost-optimizer` on GitHub (MIT-licensed).
Run it: `python data/generate_samples.py && uvicorn app.main:app`
then open <http://localhost:8000>.

Questions?
