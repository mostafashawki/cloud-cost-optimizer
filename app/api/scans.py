"""Scan-related routes (SPEC §6).

Wired into the app in `app/main.py` via `app.include_router(scans.router)`.
Handlers are intentionally thin — every interesting decision lives in
`app/services.py:run_scan` or in the schema classmethods.

Dependency injection uses the modern `Annotated[T, Depends(...)]` style so
ruff's B008 (no function-calls-in-defaults) is satisfied while keeping the
FastAPI wiring legible.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Finding, Scan
from app.schemas import FindingOut, ScanAggregations, ScanSummary
from app.services import IngestionError, UnknownProviderError, run_scan

router = APIRouter(tags=["scans"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/scans", response_model=ScanSummary, status_code=status.HTTP_200_OK)
async def create_scan(
    db: DbSession,
    file: Annotated[UploadFile, File()],
    provider: Annotated[str, Form()],
) -> ScanSummary:
    """Upload a billing CSV, run detection, persist, return summary."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uploaded file is empty",
        )

    try:
        scan = run_scan(
            db,
            file_bytes=file_bytes,
            filename=file.filename or "upload.csv",
            provider=provider,
        )
    except UnknownProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IngestionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return ScanSummary.from_scan(scan)


@router.get("/scans", response_model=list[ScanSummary])
def list_scans(db: DbSession) -> list[ScanSummary]:
    """Newest scans first."""
    scans = db.scalars(select(Scan).order_by(Scan.created_at.desc())).all()
    return [ScanSummary.from_scan(s) for s in scans]


@router.get("/scans/{scan_id}", response_model=ScanSummary)
def get_scan(scan_id: int, db: DbSession) -> ScanSummary:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scan {scan_id} not found",
        )
    return ScanSummary.from_scan(scan)


@router.get("/scans/{scan_id}/findings", response_model=list[FindingOut])
def list_findings(scan_id: int, db: DbSession) -> list[FindingOut]:
    """All findings for one scan, joined with their resource for display."""
    if db.get(Scan, scan_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scan {scan_id} not found",
        )
    findings = db.scalars(
        select(Finding).where(Finding.scan_id == scan_id).order_by(Finding.id.asc())
    ).all()
    return [FindingOut.from_orm_finding(f) for f in findings]


@router.get("/scans/{scan_id}/summary", response_model=ScanAggregations)
def scan_summary(scan_id: int, db: DbSession) -> ScanAggregations:
    """Aggregations powering the dashboard's KPI cards + bar chart."""
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"scan {scan_id} not found",
        )

    by_resource_type: dict[str, float] = {}
    by_severity: dict[str, int] = {}
    for finding in scan.findings:
        rtype = finding.resource.resource_type
        by_resource_type[rtype] = (
            by_resource_type.get(rtype, 0.0) + finding.estimated_monthly_savings
        )
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1

    # Round savings totals at the JSON boundary (python-implementer skill).
    by_resource_type = {k: round(v, 2) for k, v in by_resource_type.items()}

    return ScanAggregations(
        total_monthly_savings=round(scan.total_monthly_savings, 2),
        by_resource_type=by_resource_type,
        by_severity=by_severity,
    )
