"""End-to-end API tests (SPEC §6).

The full flow asserted here:
  POST /scans (sample_aws_cur.csv, provider=aws)
    -> persists Scan + Resources + Findings
    -> returns ScanSummary with total_monthly_savings > 0
  GET /scans/{id}/findings
    -> seeded EBS orphan present with correct remediation_command
  GET /scans/{id}/summary
    -> by_resource_type and by_severity aggregations correct

With all six SPEC §5 rules active (T7), the AWS sample produces 4 findings
totalling $43.15 and the Azure sample produces 2 findings totalling $47.76 —
those exact numbers are asserted below, per `data/EXPECTED.md`.

Note on `today`: rules read the wall clock when no `today` is injected, and
the API doesn't expose that knob. The planted orphan dates in
`data/generate_samples.py` are offset from 2026-05-30 such that every
date-threshold rule fires for any real `today` >= 2026-05-30 (i.e. the
project's current date and beyond) — so the API tests below remain
deterministic without freezing time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_AWS = PROJECT_ROOT / "data" / "sample_aws_cur.csv"
SAMPLE_AZURE = PROJECT_ROOT / "data" / "sample_azure.csv"


def _post_aws_sample(client: TestClient) -> dict:
    with SAMPLE_AWS.open("rb") as fh:
        response = client.post(
            "/scans",
            files={"file": ("sample_aws_cur.csv", fh, "text/csv")},
            data={"provider": "aws"},
        )
    assert response.status_code == 200, response.text
    return response.json()


def _post_azure_sample(client: TestClient) -> dict:
    with SAMPLE_AZURE.open("rb") as fh:
        response = client.post(
            "/scans",
            files={"file": ("sample_azure.csv", fh, "text/csv")},
            data={"provider": "azure"},
        )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Health (sanity)
# --------------------------------------------------------------------------- #


def test_health_endpoint_still_works_with_db_swapped(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --------------------------------------------------------------------------- #
# POST /scans — the headline acceptance criterion
# --------------------------------------------------------------------------- #


def test_post_scans_with_aws_sample_returns_full_summary(client: TestClient) -> None:
    body = _post_aws_sample(client)

    # data/EXPECTED.md — AWS sample: 8 resources, 4 planted orphans (one per
    # AWS rule), AWS subtotal $43.15.
    assert body["source_filename"] == "sample_aws_cur.csv"
    assert body["provider"] == "aws"
    assert body["resource_count"] == 8
    assert body["finding_count"] == 4
    assert body["total_monthly_savings"] == pytest.approx(43.15, abs=0.01)
    assert isinstance(body["scan_id"], int)
    assert "created_at" in body


def test_post_scans_with_azure_sample_returns_full_summary(client: TestClient) -> None:
    body = _post_azure_sample(client)

    # data/EXPECTED.md — Azure sample: 4 resources, 2 planted orphans
    # (one per Azure rule), Azure subtotal $47.76.
    assert body["source_filename"] == "sample_azure.csv"
    assert body["provider"] == "azure"
    assert body["resource_count"] == 4
    assert body["finding_count"] == 2
    assert body["total_monthly_savings"] == pytest.approx(47.76, abs=0.01)


def test_post_scans_rejects_unknown_provider_with_400(client: TestClient) -> None:
    response = client.post(
        "/scans",
        files={"file": ("x.csv", b"col1\nval1", "text/csv")},
        data={"provider": "gcp"},
    )

    assert response.status_code == 400
    assert "gcp" in response.json()["detail"]


def test_post_scans_rejects_empty_file_with_400(client: TestClient) -> None:
    response = client.post(
        "/scans",
        files={"file": ("empty.csv", b"", "text/csv")},
        data={"provider": "aws"},
    )

    assert response.status_code == 400


def test_post_scans_rejects_csv_with_missing_columns_with_400(client: TestClient) -> None:
    response = client.post(
        "/scans",
        files={"file": ("bad.csv", b"foo,bar\n1,2\n", "text/csv")},
        data={"provider": "aws"},
    )

    assert response.status_code == 400


# --------------------------------------------------------------------------- #
# GET /scans + GET /scans/{id}
# --------------------------------------------------------------------------- #


def test_list_scans_includes_just_created_scan(client: TestClient) -> None:
    created = _post_aws_sample(client)

    listing = client.get("/scans")

    assert listing.status_code == 200
    items = listing.json()
    assert any(item["scan_id"] == created["scan_id"] for item in items)


def test_get_scan_by_id_returns_the_scan(client: TestClient) -> None:
    created = _post_aws_sample(client)

    response = client.get(f"/scans/{created['scan_id']}")

    assert response.status_code == 200
    assert response.json()["scan_id"] == created["scan_id"]
    assert response.json()["source_filename"] == "sample_aws_cur.csv"


def test_get_scan_by_id_returns_404_for_missing_scan(client: TestClient) -> None:
    response = client.get("/scans/99999")

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# GET /scans/{id}/findings — orphan must surface with its command
# --------------------------------------------------------------------------- #


def test_seeded_ebs_orphan_appears_in_findings_with_correct_command(
    client: TestClient,
) -> None:
    created = _post_aws_sample(client)

    findings = client.get(f"/scans/{created['scan_id']}/findings")
    assert findings.status_code == 200
    items = findings.json()

    matches = [it for it in items if it["resource_id"] == "vol-0unattachedebs00001"]
    assert len(matches) == 1, f"expected one EBS-orphan finding, got {len(matches)}"
    orphan = matches[0]

    assert orphan["rule_id"] == "aws_unattached_ebs_volume"
    assert orphan["severity"] == "high"
    assert orphan["estimated_monthly_savings"] == pytest.approx(12.00)
    assert orphan["resource_type"] == "ebs_volume"
    assert orphan["provider"] == "aws"
    assert orphan["region"] == "us-east-1"
    assert orphan["remediation_command"] == (
        "aws ec2 delete-volume --volume-id vol-0unattachedebs00001 --region us-east-1"
    )


def test_findings_for_missing_scan_returns_404(client: TestClient) -> None:
    response = client.get("/scans/99999/findings")

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# GET /scans/{id}/summary — aggregations
# --------------------------------------------------------------------------- #


def test_aws_summary_aggregates_by_resource_type_and_severity(client: TestClient) -> None:
    created = _post_aws_sample(client)

    response = client.get(f"/scans/{created['scan_id']}/summary")
    assert response.status_code == 200
    body = response.json()

    # Per data/EXPECTED.md with all six rules active.
    assert body["total_monthly_savings"] == pytest.approx(43.15, abs=0.01)
    assert body["by_resource_type"] == {
        "ebs_volume": pytest.approx(12.00),
        "ec2_instance": pytest.approx(25.00),
        "elastic_ip": pytest.approx(3.65),
        "ebs_snapshot": pytest.approx(2.50),
    }
    # EBS + EIP are high; stopped EC2 is medium; orphaned snapshot is low.
    assert body["by_severity"] == {"high": 2, "medium": 1, "low": 1}


def test_azure_summary_aggregates_by_resource_type_and_severity(client: TestClient) -> None:
    created = _post_azure_sample(client)

    response = client.get(f"/scans/{created['scan_id']}/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["total_monthly_savings"] == pytest.approx(47.76, abs=0.01)
    assert body["by_resource_type"] == {
        "managed_disk": pytest.approx(5.76),
        "virtual_machine": pytest.approx(42.00),
    }
    # Unattached disk is high; deallocated VM is medium.
    assert body["by_severity"] == {"high": 1, "medium": 1}


def test_summary_for_missing_scan_returns_404(client: TestClient) -> None:
    response = client.get("/scans/99999/summary")

    assert response.status_code == 404
