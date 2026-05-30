"""Pydantic v2 request/response schemas (SPEC §6).

Schemas are deliberately small and *flat* (no nested ORM objects) — the
dashboard JS is hand-written and a flat shape is easier to consume than a
graph.

`from_scan` / `from_orm_finding` classmethods build the schema from the
SQLAlchemy ORM rows. I avoid `from_attributes=True` here because (a) the
`ScanSummary.scan_id` field is named differently from the ORM column `id`,
and (b) `FindingOut` joins fields from the related `Resource` row, which the
default attribute-mode adapter doesn't handle.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models import Finding as FindingORM
    from app.models import Scan

Provider = Literal["aws", "azure"]
Severity = Literal["low", "medium", "high"]


class ScanSummary(BaseModel):
    """The shape returned by every endpoint that produces a scan reference
    (`POST /scans`, `GET /scans`, `GET /scans/{id}`)."""

    scan_id: int
    source_filename: str
    provider: Provider
    resource_count: int
    finding_count: int
    total_monthly_savings: float
    created_at: datetime

    @classmethod
    def from_scan(cls, scan: Scan) -> ScanSummary:
        return cls(
            scan_id=scan.id,
            source_filename=scan.source_filename,
            provider=scan.provider,  # type: ignore[arg-type]
            resource_count=scan.resource_count,
            finding_count=scan.finding_count,
            total_monthly_savings=round(scan.total_monthly_savings, 2),
            created_at=scan.created_at,
        )


class FindingOut(BaseModel):
    """One row in the findings table; joins useful fields from the related
    `Resource` so the dashboard doesn't have to do a second hop."""

    id: int
    rule_id: str
    title: str
    reason: str
    severity: Severity
    estimated_monthly_savings: float
    remediation_command: str
    resource_id: str
    resource_type: str
    provider: Provider
    region: str

    @classmethod
    def from_orm_finding(cls, finding: FindingORM) -> FindingOut:
        resource = finding.resource
        return cls(
            id=finding.id,
            rule_id=finding.rule_id,
            title=finding.title,
            reason=finding.reason,
            severity=finding.severity,  # type: ignore[arg-type]
            estimated_monthly_savings=round(finding.estimated_monthly_savings, 2),
            remediation_command=finding.remediation_command,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            provider=resource.provider,  # type: ignore[arg-type]
            region=resource.region,
        )


class ScanAggregations(BaseModel):
    """`GET /scans/{id}/summary` — the aggregations the dashboard charts."""

    total_monthly_savings: float
    by_resource_type: dict[str, float] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
