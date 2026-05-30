"""Tests for app/models.py — ORM table creation and round-trip persistence.

These tests intentionally use an in-memory SQLite engine (not the project-level
`app.db.engine`) so they're hermetic and never touch the real `app.db` file.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Finding, Resource, Scan


@pytest.fixture
def engine() -> Engine:
    eng = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    return eng


def test_create_all_creates_tables(engine: Engine) -> None:
    table_names = set(inspect(engine).get_table_names())

    assert {"scans", "resources", "findings"} <= table_names


def test_insert_and_read_finding(engine: Engine) -> None:
    with Session(engine) as session:
        scan = Scan(
            source_filename="sample_aws_cur.csv",
            provider="aws",
            resource_count=1,
            finding_count=1,
            total_monthly_savings=12.34,
        )
        resource = Resource(
            scan=scan,
            provider="aws",
            resource_id="vol-0123456789abcdef0",
            resource_type="ebs_volume",
            region="us-east-1",
            status="available",
            monthly_cost=12.34,
            attached=False,
            last_activity_date=date(2026, 4, 1),
            tags={"env": "prod", "owner": "platform"},
            raw={"line_item_usage_type": "EBS:VolumeUsage.gp3"},
        )
        finding = Finding(
            scan=scan,
            resource=resource,
            rule_id="aws_unattached_ebs_volume",
            title="Unattached EBS volume",
            reason="EBS volume in status=available has no attachments",
            severity="high",
            estimated_monthly_savings=12.34,
            remediation_command=(
                "aws ec2 delete-volume --volume-id vol-0123456789abcdef0 --region us-east-1"
            ),
        )
        session.add(scan)
        session.commit()

        scan_pk = scan.id
        resource_pk = resource.id
        finding_pk = finding.id

    with Session(engine) as session:
        loaded = session.get(Scan, scan_pk)
        assert loaded is not None
        assert loaded.source_filename == "sample_aws_cur.csv"
        assert loaded.provider == "aws"
        assert loaded.resource_count == 1
        assert loaded.finding_count == 1
        assert loaded.total_monthly_savings == pytest.approx(12.34)
        assert loaded.created_at is not None

        assert len(loaded.resources) == 1
        r = loaded.resources[0]
        assert r.id == resource_pk
        assert r.resource_id == "vol-0123456789abcdef0"
        assert r.resource_type == "ebs_volume"
        assert r.region == "us-east-1"
        assert r.status == "available"
        assert r.attached is False
        assert r.last_activity_date == date(2026, 4, 1)
        assert r.tags == {"env": "prod", "owner": "platform"}
        assert r.raw == {"line_item_usage_type": "EBS:VolumeUsage.gp3"}

        assert len(loaded.findings) == 1
        f = loaded.findings[0]
        assert f.id == finding_pk
        assert f.rule_id == "aws_unattached_ebs_volume"
        assert f.severity == "high"
        assert f.estimated_monthly_savings == pytest.approx(12.34)
        assert f.remediation_command == (
            "aws ec2 delete-volume --volume-id vol-0123456789abcdef0 --region us-east-1"
        )

        assert f.scan.id == loaded.id
        assert f.resource.id == r.id
        assert r.findings[0].id == f.id
