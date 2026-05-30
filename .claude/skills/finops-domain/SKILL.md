---
name: finops-domain
description: "Use whenever working on cloud cost / FinOps logic in this repo — defining input file schemas (AWS CUR, Azure cost export, resource inventory), implementing or reviewing the detection rules R1-R6, computing monthly savings, or generating decommission CLI commands. Load for tasks T2 (sample data), T4 (detection), and T5 (remediation)."
---

# FinOps Domain Knowledge

Authoritative reference for the cloud-waste logic. Pair with `docs/SPEC.md` (§2, §4, §5).

## Input schemas

**AWS Cost & Usage Report (CUR) — CSV.** One row per resource per usage type per period.
Columns this project relies on: `lineItem/ResourceId`, `lineItem/ProductCode` (e.g. `AmazonEC2`),
`lineItem/UsageType` (e.g. `EBS:VolumeUsage.gp3`, `ElasticIP:IdleAddress`), `lineItem/UsageAmount`,
`lineItem/UnblendedCost`, `product/region`, `bill/BillingPeriodStartDate`. A zero `UsageAmount` with
positive `UnblendedCost` is the classic idle signal.

**Azure cost export — CSV.** Columns: `ResourceId`, `MeterCategory`, `ResourceGroup`, `Quantity`,
`CostInBillingCurrency`, `ResourceLocation`, `Date`.

**Resource inventory — JSON.** Billing tells you cost; inventory tells you *state*, which is what
makes a resource "orphaned". Mirror the shape of `describe-*` output:
- `volumes[]`: `{volume_id, state: "available"|"in-use", size_gb, region, create_time, attachments[]}`
- `addresses[]` (EIP): `{allocation_id, public_ip, association_id|null, instance_id|null}`
- `instances[]`: `{instance_id, state: "running"|"stopped", stopped_since|null, attached_volumes[]}`
- `snapshots[]`: `{snapshot_id, source_volume_id|null, start_time, size_gb}`
- Azure: `disks[]` (`state: "Unattached"|"Attached"`), `public_ips[]` (`associated: bool`),
  `vms[]` (`state: "running"|"deallocated"`).

Join key between the two artifacts is the resource id (`lineItem/ResourceId` ↔ inventory id).

## Why "orphaned" needs both files
A volume costs money whether attached or not, so billing alone shows the cost but not the waste.
Only the inventory `state == "available"` proves nothing is using it. Always reason from
**state (inventory) → confirmed waste**, then **attach the dollar figure (billing)**.

## Detection rules (deterministic)
| ID | Condition | Monthly savings | Destructive? |
|----|-----------|-----------------|--------------|
| R1 | volume `state == available` | matched storage cost, else `size_gb * 0.08` | no |
| R2 | EIP `association_id is None` | matched cost, else `0.005 * 730 ≈ 3.65` | no |
| R3 | instance `stopped` and `stopped_since` > 30d | Σ attached-volume monthly cost | **yes** |
| R4 | snapshot `source_volume_id` absent from current volumes (or null) and age > 30d | `size_gb * 0.05` | no |
| R5 | billing line `unblended_cost > 0` and `usage_amount == 0` | the line cost | no |
| R6 | Azure: disk `Unattached` / public_ip not associated / vm `deallocated` w/ disks | matched Azure cost | mixed |

Fallback unit prices (`gp3 $0.08/GB-mo`, `snapshot $0.05/GB-mo`, `idle EIP $0.005/hr`) are public
list-price approximations — keep them as named constants with a comment, never silent magic numbers.
Round savings to 2 decimals at the output boundary. Severity suggestion: `high ≥ $50/mo`,
`medium ≥ $10`, else `low` (tune to the planted data so the demo shows a spread).

## Remediation command templates (generate as strings — never execute)
- R1: `aws ec2 delete-volume --volume-id <volume_id>`
- R2: `aws ec2 release-address --allocation-id <allocation_id>`
- R3: `aws ec2 create-snapshot --volume-id <vol> --description "pre-terminate <instance_id>"` then
  `aws ec2 terminate-instances --instance-ids <instance_id>`  *(destructive)*
- R4: `aws ec2 delete-snapshot --snapshot-id <snapshot_id>`
- R5: emit `# investigate idle resource: <resource_id>` (no destructive command)
- Azure: `az disk delete --ids <id> --yes`, `az network public-ip delete --ids <id>`,
  `az vm delete --ids <id> --yes`, `az snapshot delete --ids <id>`

`remediation.sh` starts with a banner: `set -euo pipefail` plus a comment block stating the commands
are DESTRUCTIVE and require human review. Destructive lines are commented out unless the script is
generated with `confirm=true`. This module imports no `boto3`/`azure` SDK and calls no subprocess.

## Common mistakes to avoid
- Flagging `in-use` volumes or `running` instances (false positives — tests will catch this).
- Using `UsageAmount` as cost (cost is `UnblendedCost`).
- Treating an EIP attached to a *running* instance as idle (only `association_id is None` is idle).
- Forgetting that a snapshot whose source volume still exists is NOT orphaned.
