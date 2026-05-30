"""Generate synthetic AWS CUR + Azure billing export CSVs with planted orphans.

Why this module exists
----------------------
The optimizer is fully offline (SPEC §1) — it never queries a cloud account. The
detection rules in `app/rules/catalog.py` need realistic billing CSVs with known
*wasted* resources to:

  * exercise every rule R1-R6 in SPEC §5,
  * give the dashboard demo a believable dollar figure, and
  * let the test suite assert exact savings totals against a planted contract
    documented in `data/EXPECTED.md`.

Design choices
--------------
* **Deterministic.** No RNG; fixed `TODAY = 2026-05-30` reference date so age
  thresholds (R2 stopped > 30d, R4 snapshot > 90d, R6 deallocated > 30d) are
  stable across runs and matchable in tests.
* **Single-file-per-provider.** SPEC §3 only ships two CSVs, not a separate
  inventory JSON, so resource *state* (available/stopped/unassociated/...) and
  *attached*/*last_activity_date* travel as extra `resource/*` columns on the
  AWS CUR rows (and analogous `ResourceType`/`ResourceStatus`/...
  columns on the Azure rows). Real exports don't have these — they'd come from
  joining billing with `describe-*` output — but inlining the state keeps the
  MVP parser uncomplicated.
* **Stable, recognisable IDs.** Every planted orphan has an ID with the word
  describing its waste (`vol-0unattachedebs00001`, `vm-deallocated-demo-001`,
  ...) so a human eyeballing the CSV can spot them.

Run from the project root:
    python data/generate_samples.py
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
DEFAULT_AWS_OUT = DATA_DIR / "sample_aws_cur.csv"
DEFAULT_AZURE_OUT = DATA_DIR / "sample_azure.csv"

# Reference "today" for every dated row. Keeping this fixed (NOT
# `date.today()`) makes the generator output bit-for-bit reproducible and lets
# `data/EXPECTED.md` lock in age-based rule outcomes for the test suite.
TODAY: date = date(2026, 5, 30)
BILLING_PERIOD_START: date = TODAY.replace(day=1)


def _iso(d: date | None) -> str:
    return d.isoformat() if d else ""


# --------------------------------------------------------------------------- #
# AWS Cost & Usage Report
# --------------------------------------------------------------------------- #

AWS_HEADERS: list[str] = [
    # Real CUR columns (subset this project relies on, per finops-domain skill).
    "bill/BillingPeriodStartDate",
    "lineItem/ResourceId",
    "lineItem/ProductCode",
    "lineItem/UsageType",
    "lineItem/UsageAmount",
    "lineItem/UnblendedCost",
    "product/region",
    # Extended state columns — see module docstring for rationale.
    "resource/type",
    "resource/status",
    "resource/attached",
    "resource/last_activity_date",
    "resource/tags",
]


def aws_rows() -> list[dict[str, str]]:
    bp = _iso(BILLING_PERIOD_START)
    rows: list[dict[str, str]] = []

    # --- Planted orphans (one per AWS rule in SPEC §5) ---

    # SPEC #1 R1 — unattached EBS volume (status=available). Savings = full cost.
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "vol-0unattachedebs00001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "EBS:VolumeUsage.gp3",
            "lineItem/UsageAmount": "150.000",  # GB-month
            "lineItem/UnblendedCost": "12.00",
            "product/region": "us-east-1",
            "resource/type": "ebs_volume",
            "resource/status": "available",
            "resource/attached": "false",
            "resource/last_activity_date": _iso(TODAY - timedelta(days=20)),
            "resource/tags": "env=dev;owner=alice",
        }
    )

    # SPEC #2 R2 — idle stopped EC2 (stopped > 30d). Savings = monthly cost.
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "i-0longstoppedec2001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "BoxUsage:t3.medium",
            "lineItem/UsageAmount": "0.0",  # stopped: no compute hours
            "lineItem/UnblendedCost": "25.00",  # root EBS / reservations still bill
            "product/region": "us-east-1",
            "resource/type": "ec2_instance",
            "resource/status": "stopped",
            "resource/attached": "true",
            "resource/last_activity_date": _iso(TODAY - timedelta(days=80)),
            "resource/tags": "env=staging;owner=bob",
        }
    )

    # SPEC #3 R3 — unassociated Elastic IP. Savings = idle EIP cost.
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "eipalloc-0unassociated001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "ElasticIP:IdleAddress",
            "lineItem/UsageAmount": "730.0",  # hours/month
            "lineItem/UnblendedCost": "3.65",
            "product/region": "us-east-1",
            "resource/type": "elastic_ip",
            "resource/status": "unassociated",
            "resource/attached": "false",
            "resource/last_activity_date": _iso(TODAY - timedelta(days=45)),
            "resource/tags": "",
        }
    )

    # SPEC #4 R4 — orphaned snapshot (attached=false, age > 90d).
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "snap-0orphanedsnap00001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "EBS:SnapshotUsage",
            "lineItem/UsageAmount": "50.0",
            "lineItem/UnblendedCost": "2.50",
            "product/region": "us-east-1",
            "resource/type": "ebs_snapshot",
            "resource/status": "completed",
            "resource/attached": "false",
            "resource/last_activity_date": _iso(TODAY - timedelta(days=150)),
            "resource/tags": "purpose=backup",
        }
    )

    # --- Healthy rows (must NOT be flagged by any rule) ---

    # In-use EBS volume.
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "vol-0healthyinuse00001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "EBS:VolumeUsage.gp3",
            "lineItem/UsageAmount": "100.0",
            "lineItem/UnblendedCost": "8.00",
            "product/region": "us-east-1",
            "resource/type": "ebs_volume",
            "resource/status": "in-use",
            "resource/attached": "true",
            "resource/last_activity_date": _iso(TODAY - timedelta(days=1)),
            "resource/tags": "env=prod",
        }
    )

    # Running EC2.
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "i-0runninginst00001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "BoxUsage:t3.small",
            "lineItem/UsageAmount": "730.0",
            "lineItem/UnblendedCost": "30.00",
            "product/region": "us-east-1",
            "resource/type": "ec2_instance",
            "resource/status": "running",
            "resource/attached": "true",
            "resource/last_activity_date": _iso(TODAY),
            "resource/tags": "env=prod;owner=carol",
        }
    )

    # Associated EIP (free while attached to a running instance).
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "eipalloc-0associated001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "ElasticIP:InUseAddress",
            "lineItem/UsageAmount": "730.0",
            "lineItem/UnblendedCost": "0.00",
            "product/region": "us-east-1",
            "resource/type": "elastic_ip",
            "resource/status": "associated",
            "resource/attached": "true",
            "resource/last_activity_date": _iso(TODAY),
            "resource/tags": "",
        }
    )

    # Recent snapshot with parent (attached=true, fresh) — does NOT match R4.
    rows.append(
        {
            "bill/BillingPeriodStartDate": bp,
            "lineItem/ResourceId": "snap-0recentsnap00001",
            "lineItem/ProductCode": "AmazonEC2",
            "lineItem/UsageType": "EBS:SnapshotUsage",
            "lineItem/UsageAmount": "40.0",
            "lineItem/UnblendedCost": "2.00",
            "product/region": "us-east-1",
            "resource/type": "ebs_snapshot",
            "resource/status": "completed",
            "resource/attached": "true",
            "resource/last_activity_date": _iso(TODAY - timedelta(days=10)),
            "resource/tags": "purpose=backup",
        }
    )

    return rows


# --------------------------------------------------------------------------- #
# Azure cost export
# --------------------------------------------------------------------------- #

AZURE_HEADERS: list[str] = [
    "Date",
    "ResourceId",
    "MeterCategory",
    "MeterSubcategory",
    "ResourceGroup",
    "ResourceLocation",
    "Quantity",
    "CostInBillingCurrency",
    "Tags",
    # Extended state columns.
    "ResourceType",
    "ResourceStatus",
    "Attached",
    "LastActivityDate",
]

AZ_SUB = "00000000-0000-0000-0000-000000000000"
AZ_RG = "rg-demo"

_AZ_PROVIDER_PATH = {
    "managed_disk": "Microsoft.Compute/disks",
    "virtual_machine": "Microsoft.Compute/virtualMachines",
    "public_ip": "Microsoft.Network/publicIPAddresses",
}


def _az_id(kind: str, name: str) -> str:
    return (
        f"/subscriptions/{AZ_SUB}/resourceGroups/{AZ_RG}"
        f"/providers/{_AZ_PROVIDER_PATH[kind]}/{name}"
    )


def azure_rows() -> list[dict[str, str]]:
    today_iso = _iso(TODAY)
    rows: list[dict[str, str]] = []

    # --- Planted orphans ---

    # SPEC #5 — unattached managed disk.
    rows.append(
        {
            "Date": today_iso,
            "ResourceId": _az_id("managed_disk", "disk-unattached-demo-001"),
            "MeterCategory": "Storage",
            "MeterSubcategory": "Premium SSD Managed Disks",
            "ResourceGroup": AZ_RG,
            "ResourceLocation": "eastus",
            "Quantity": "1.0",
            "CostInBillingCurrency": "5.76",
            "Tags": "env:dev;owner:diana",
            "ResourceType": "managed_disk",
            "ResourceStatus": "unattached",
            "Attached": "false",
            "LastActivityDate": _iso(TODAY - timedelta(days=15)),
        }
    )

    # SPEC #6 — deallocated VM (> 30d).
    rows.append(
        {
            "Date": today_iso,
            "ResourceId": _az_id("virtual_machine", "vm-deallocated-demo-001"),
            "MeterCategory": "Virtual Machines",
            "MeterSubcategory": "B-Series Burstable",
            "ResourceGroup": AZ_RG,
            "ResourceLocation": "eastus",
            "Quantity": "0.0",
            "CostInBillingCurrency": "42.00",
            "Tags": "env:staging;owner:erik",
            "ResourceType": "virtual_machine",
            "ResourceStatus": "deallocated",
            "Attached": "true",
            "LastActivityDate": _iso(TODAY - timedelta(days=60)),
        }
    )

    # --- Healthy rows ---

    # Attached managed disk.
    rows.append(
        {
            "Date": today_iso,
            "ResourceId": _az_id("managed_disk", "disk-attached-demo-001"),
            "MeterCategory": "Storage",
            "MeterSubcategory": "Premium SSD Managed Disks",
            "ResourceGroup": AZ_RG,
            "ResourceLocation": "eastus",
            "Quantity": "1.0",
            "CostInBillingCurrency": "8.00",
            "Tags": "env:prod",
            "ResourceType": "managed_disk",
            "ResourceStatus": "attached",
            "Attached": "true",
            "LastActivityDate": today_iso,
        }
    )

    # Running VM.
    rows.append(
        {
            "Date": today_iso,
            "ResourceId": _az_id("virtual_machine", "vm-running-demo-001"),
            "MeterCategory": "Virtual Machines",
            "MeterSubcategory": "Standard_D2s_v3",
            "ResourceGroup": AZ_RG,
            "ResourceLocation": "eastus",
            "Quantity": "730.0",
            "CostInBillingCurrency": "70.00",
            "Tags": "env:prod;owner:frank",
            "ResourceType": "virtual_machine",
            "ResourceStatus": "running",
            "Attached": "true",
            "LastActivityDate": today_iso,
        }
    )

    return rows


# --------------------------------------------------------------------------- #
# CSV writer / CLI
# --------------------------------------------------------------------------- #


def _write_csv(path: Path, headers: list[str], rows: Iterable[dict[str, str]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            n += 1
    return n


def write_samples(aws_out: Path, azure_out: Path) -> tuple[int, int]:
    """Write both CSVs and return (aws_row_count, azure_row_count)."""
    aws_n = _write_csv(aws_out, AWS_HEADERS, aws_rows())
    az_n = _write_csv(azure_out, AZURE_HEADERS, azure_rows())
    return aws_n, az_n


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate sample AWS CUR + Azure billing CSVs.")
    parser.add_argument("--aws-out", type=Path, default=DEFAULT_AWS_OUT)
    parser.add_argument("--azure-out", type=Path, default=DEFAULT_AZURE_OUT)
    args = parser.parse_args()
    aws_n, az_n = write_samples(args.aws_out, args.azure_out)
    print(f"Wrote {args.aws_out} ({aws_n} rows)")
    print(f"Wrote {args.azure_out} ({az_n} rows)")


if __name__ == "__main__":
    main()
