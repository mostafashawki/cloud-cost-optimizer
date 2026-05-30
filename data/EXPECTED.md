# `data/` — Expected planted orphans & totals

The generator at `data/generate_samples.py` is **deterministic** (no RNG;
`TODAY = 2026-05-30` baked in). This file is the contract the test suite asserts
against — exact orphan IDs, exact severities, exact dollar amounts.

## AWS — `sample_aws_cur.csv`

| Planted orphan ID | Resource type | Status / age | SPEC §5 rule | Severity | Monthly savings |
|---|---|---|---|---|---:|
| `vol-0unattachedebs00001` | `ebs_volume` | available | `aws_unattached_ebs_volume` | high | $12.00 |
| `i-0longstoppedec2001` | `ec2_instance` | stopped, 80d ago | `aws_idle_stopped_ec2` | medium | $25.00 |
| `eipalloc-0unassociated001` | `elastic_ip` | unassociated | `aws_unassociated_elastic_ip` | high | $3.65 |
| `snap-0orphanedsnap00001` | `ebs_snapshot` | orphaned, 150d ago | `aws_orphaned_snapshot` | low | $2.50 |
|  |  |  |  | **AWS subtotal** | **$43.15** |

Healthy AWS rows in the same file (must NOT trigger any rule):

| Healthy ID | Resource type | Status |
|---|---|---|
| `vol-0healthyinuse00001` | `ebs_volume` | in-use |
| `i-0runninginst00001` | `ec2_instance` | running |
| `eipalloc-0associated001` | `elastic_ip` | associated |
| `snap-0recentsnap00001` | `ebs_snapshot` | attached / recent |

**AWS rows total: 8** (4 planted orphans + 4 healthy).

## Azure — `sample_azure.csv`

| Planted orphan (resource name suffix) | Resource type | Status / age | SPEC §5 rule | Severity | Monthly savings |
|---|---|---|---|---|---:|
| `disk-unattached-demo-001` | `managed_disk` | unattached | `azure_unattached_managed_disk` | high | $5.76 |
| `vm-deallocated-demo-001` | `virtual_machine` | deallocated, 60d ago | `azure_deallocated_vm` | medium | $42.00 |
|  |  |  |  | **Azure subtotal** | **$47.76** |

Healthy Azure rows in the same file (must NOT trigger any rule):

| Healthy resource name suffix | Resource type | Status |
|---|---|---|
| `disk-attached-demo-001` | `managed_disk` | attached |
| `vm-running-demo-001` | `virtual_machine` | running |

**Azure rows total: 4** (2 planted orphans + 2 healthy).

## Grand totals (asserted by `tests/test_samples.py` and later by detection tests)

| Metric | Expected value |
|---|---:|
| Planted orphans across both providers | **6** |
| AWS savings subtotal | **$43.15** |
| Azure savings subtotal | **$47.76** |
| **Total monthly savings if every orphan is decommissioned** | **$90.91** |

Rule → planted orphan mapping (one orphan per rule, so each rule's positive test
has a known target):

| SPEC §5 rule | Planted orphan |
|---|---|
| 1. `aws_unattached_ebs_volume` | `vol-0unattachedebs00001` |
| 2. `aws_idle_stopped_ec2` | `i-0longstoppedec2001` |
| 3. `aws_unassociated_elastic_ip` | `eipalloc-0unassociated001` |
| 4. `aws_orphaned_snapshot` | `snap-0orphanedsnap00001` |
| 5. `azure_unattached_managed_disk` | resource name `disk-unattached-demo-001` |
| 6. `azure_deallocated_vm` | resource name `vm-deallocated-demo-001` |
