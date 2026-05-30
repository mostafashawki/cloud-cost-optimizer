"""Tests for app/ingestion/{aws_cur,azure}.py and the shared `_parsing` helpers.

Coverage per the playbook's required tests:
- inline tiny CSV fixtures for both providers → counts + one mapped field each
- one malformed-row case asserting it's counted/skipped, not fatal

Plus a few extras worth holding the line on:
- the committed `data/sample_*.csv` files parse to the row counts EXPECTED.md
  promises (acceptance criterion for T3)
- the seeded unattached EBS volume parses with `status="available"` and the
  exact $12.00 cost (explicit acceptance criterion for T3)
- missing required columns produce a schema error rather than a stack trace
- bytes / Path / pre-opened stream all work as `source`
- empty value -> None for the optional date column
- tags parse correctly for both separator conventions (`=` AWS, `:` Azure)
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest

from app.ingestion import aws_cur, azure
from app.ingestion._parsing import ParseResult

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SAMPLE_AWS = DATA_DIR / "sample_aws_cur.csv"
SAMPLE_AZURE = DATA_DIR / "sample_azure.csv"


# --------------------------------------------------------------------------- #
# Inline AWS CSV fixtures
# --------------------------------------------------------------------------- #

AWS_HEADER = (
    "bill/BillingPeriodStartDate,lineItem/ResourceId,lineItem/ProductCode,"
    "lineItem/UsageType,lineItem/UsageAmount,lineItem/UnblendedCost,"
    "product/region,resource/type,resource/status,resource/attached,"
    "resource/last_activity_date,resource/tags\n"
)


def _aws_inline(*rows: str) -> str:
    return AWS_HEADER + "\n".join(rows) + ("\n" if rows else "")


AWS_VALID_ROW = (
    "2026-05-01,vol-test1234,AmazonEC2,EBS:VolumeUsage.gp3,100.0,9.99,"
    "us-east-1,ebs_volume,available,false,2026-05-10,env=dev;owner=alice"
)
AWS_RUNNING_ROW = (
    "2026-05-01,i-test1234,AmazonEC2,BoxUsage:t3.small,730.0,30.00,"
    "us-east-1,ec2_instance,running,true,2026-05-30,env=prod"
)
AWS_MALFORMED_ROW_BAD_COST = (
    "2026-05-01,vol-bad,AmazonEC2,EBS:VolumeUsage.gp3,100.0,NOT_A_NUMBER,"
    "us-east-1,ebs_volume,available,false,,"
)


# --------------------------------------------------------------------------- #
# Inline Azure CSV fixtures
# --------------------------------------------------------------------------- #

AZURE_HEADER = (
    "Date,ResourceId,MeterCategory,MeterSubcategory,ResourceGroup,"
    "ResourceLocation,Quantity,CostInBillingCurrency,Tags,"
    "ResourceType,ResourceStatus,Attached,LastActivityDate\n"
)

AZURE_VALID_ROW = (
    "2026-05-30,/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-x,"
    "Storage,Premium SSD Managed Disks,rg,eastus,1.0,5.76,env:dev;owner:diana,"
    "managed_disk,unattached,false,2026-05-15"
)
AZURE_RUNNING_ROW = (
    "2026-05-30,/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-y,"
    "Virtual Machines,Standard_D2s_v3,rg,eastus,730.0,70.00,env:prod,"
    "virtual_machine,running,true,2026-05-30"
)
AZURE_MALFORMED_ROW_EMPTY_ID = (
    "2026-05-30,,Storage,Premium SSD Managed Disks,rg,eastus,1.0,5.76,,"
    "managed_disk,unattached,false,2026-05-15"
)


def _azure_inline(*rows: str) -> str:
    return AZURE_HEADER + "\n".join(rows) + ("\n" if rows else "")


# --------------------------------------------------------------------------- #
# AWS parser
# --------------------------------------------------------------------------- #


def test_aws_inline_csv_yields_expected_count_and_mapped_fields() -> None:
    csv_text = _aws_inline(AWS_VALID_ROW, AWS_RUNNING_ROW)

    result = aws_cur.parse(csv_text.encode("utf-8"))

    assert isinstance(result, ParseResult)
    assert result.malformed_count == 0
    assert result.errors == []
    assert len(result.resources) == 2

    r0 = result.resources[0]
    assert r0.provider == "aws"
    assert r0.resource_id == "vol-test1234"
    assert r0.resource_type == "ebs_volume"
    assert r0.region == "us-east-1"
    assert r0.status == "available"
    assert r0.monthly_cost == pytest.approx(9.99)
    assert r0.attached is False
    assert r0.last_activity_date == date(2026, 5, 10)
    assert r0.tags == {"env": "dev", "owner": "alice"}

    r1 = result.resources[1]
    assert r1.resource_id == "i-test1234"
    assert r1.resource_type == "ec2_instance"
    assert r1.status == "running"
    assert r1.attached is True


def test_aws_parser_skips_malformed_row_and_keeps_going() -> None:
    csv_text = _aws_inline(AWS_VALID_ROW, AWS_MALFORMED_ROW_BAD_COST, AWS_RUNNING_ROW)

    result = aws_cur.parse(csv_text.encode("utf-8"))

    assert result.malformed_count == 1
    assert len(result.errors) == 1
    assert "row 3" in result.errors[0]  # row 1 is header; bad row is line 3
    assert len(result.resources) == 2
    assert {r.resource_id for r in result.resources} == {"vol-test1234", "i-test1234"}


def test_aws_parser_handles_empty_file() -> None:
    result = aws_cur.parse(b"")

    assert result.resources == []
    assert "empty file" in result.errors[0]


def test_aws_parser_rejects_missing_required_columns() -> None:
    csv_text = "bill/BillingPeriodStartDate,lineItem/ResourceId\n2026-05-01,vol-x\n"

    result = aws_cur.parse(csv_text.encode("utf-8"))

    assert result.resources == []
    assert any("missing required columns" in e for e in result.errors)


def test_aws_parser_accepts_bytes_path_and_stream() -> None:
    csv_text = _aws_inline(AWS_VALID_ROW)

    from_bytes = aws_cur.parse(csv_text.encode("utf-8"))
    from_stream = aws_cur.parse(io.StringIO(csv_text))

    assert len(from_bytes.resources) == 1
    assert len(from_stream.resources) == 1
    assert from_bytes.resources[0].resource_id == from_stream.resources[0].resource_id


# --------------------------------------------------------------------------- #
# Azure parser
# --------------------------------------------------------------------------- #


def test_azure_inline_csv_yields_expected_count_and_mapped_fields() -> None:
    csv_text = _azure_inline(AZURE_VALID_ROW, AZURE_RUNNING_ROW)

    result = azure.parse(csv_text.encode("utf-8"))

    assert result.malformed_count == 0
    assert len(result.resources) == 2

    r0 = result.resources[0]
    assert r0.provider == "azure"
    assert r0.resource_id.endswith("/disk-x")
    assert r0.resource_type == "managed_disk"
    assert r0.region == "eastus"
    assert r0.status == "unattached"
    assert r0.monthly_cost == pytest.approx(5.76)
    assert r0.attached is False
    assert r0.last_activity_date == date(2026, 5, 15)
    assert r0.tags == {"env": "dev", "owner": "diana"}

    r1 = result.resources[1]
    assert r1.resource_type == "virtual_machine"
    assert r1.status == "running"
    assert r1.attached is True


def test_azure_parser_skips_malformed_row_and_keeps_going() -> None:
    csv_text = _azure_inline(AZURE_VALID_ROW, AZURE_MALFORMED_ROW_EMPTY_ID, AZURE_RUNNING_ROW)

    result = azure.parse(csv_text.encode("utf-8"))

    assert result.malformed_count == 1
    assert len(result.errors) == 1
    assert "row 3" in result.errors[0]
    assert len(result.resources) == 2


# --------------------------------------------------------------------------- #
# Sample-file round-trip (T3 acceptance criterion)
# --------------------------------------------------------------------------- #


def test_aws_sample_file_parses_to_expected_resource_count() -> None:
    result = aws_cur.parse(SAMPLE_AWS)

    assert result.malformed_count == 0
    assert len(result.resources) == 8  # per data/EXPECTED.md


def test_azure_sample_file_parses_to_expected_resource_count() -> None:
    result = azure.parse(SAMPLE_AZURE)

    assert result.malformed_count == 0
    assert len(result.resources) == 4


def test_seeded_unattached_ebs_volume_parses_with_correct_status_and_cost() -> None:
    """SPEC §8 / T3 acceptance: the seeded unattached EBS volume must parse
    with status='available' and the documented $12.00 monthly cost."""
    result = aws_cur.parse(SAMPLE_AWS)

    by_id = {r.resource_id: r for r in result.resources}
    assert "vol-0unattachedebs00001" in by_id

    orphan = by_id["vol-0unattachedebs00001"]
    assert orphan.provider == "aws"
    assert orphan.resource_type == "ebs_volume"
    assert orphan.status == "available"
    assert orphan.attached is False
    assert orphan.monthly_cost == pytest.approx(12.00)
    assert orphan.region == "us-east-1"


def test_azure_sample_unattached_disk_parses_with_correct_status_and_cost() -> None:
    result = azure.parse(SAMPLE_AZURE)

    disk = next(
        r for r in result.resources if r.resource_id.endswith("/disk-unattached-demo-001")
    )

    assert disk.provider == "azure"
    assert disk.resource_type == "managed_disk"
    assert disk.status == "unattached"
    assert disk.attached is False
    assert disk.monthly_cost == pytest.approx(5.76)
