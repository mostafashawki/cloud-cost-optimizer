"""Scan orchestration — the one place that glues parser, engine, remediation,
and persistence together.

Routes call `run_scan(db, file_bytes=..., filename=..., provider=...)` and get
back a persisted `Scan` ORM instance. Routes never touch parsers / engine /
remediation directly, so wiring stays in one file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.ingestion import aws_cur
from app.ingestion import azure as azure_parser
from app.ingestion._parsing import ParseResult
from app.models import Finding as FindingORM
from app.models import Resource as ResourceORM
from app.models import Scan
from app.remediation import generate as generate_remediation
from app.rules.base import run_engine

_PARSERS: dict[str, Callable[[Any], ParseResult]] = {
    "aws": aws_cur.parse,
    "azure": azure_parser.parse,
}


class UnknownProviderError(ValueError):
    """Raised when `provider` isn't one we have a parser for. Route maps to 400."""


class IngestionError(ValueError):
    """Raised when the parser returns a fatal error (empty file / missing
    required columns). Route maps to 400 so the user sees what's wrong."""


def run_scan(db: Session, *, file_bytes: bytes, filename: str, provider: str) -> Scan:
    """Ingest one billing CSV, detect waste, persist everything, return the Scan.

    Steps (each is a small layer so the failure mode is obvious from a trace):
      1. Pick the parser for the requested provider (or raise).
      2. Parse the bytes into NormalizedResources.
      3. Run the rule engine over the resources, get in-memory Findings.
      4. For each Finding, generate the remediation command string.
      5. Persist: one Scan row, one Resource row per resource, one Finding row
         per finding. Commit once at the end so an error mid-stream leaves no
         partial scan in the DB.

    Raises:
      UnknownProviderError: `provider` is not "aws" or "azure".
      IngestionError: parser produced zero usable resources (empty file, bad
        header). Distinct from "0 findings" — that's a perfectly valid scan.
    """
    parser = _PARSERS.get(provider)
    if parser is None:
        raise UnknownProviderError(
            f"unknown provider {provider!r}; expected one of {sorted(_PARSERS)}"
        )

    parse_result = parser(file_bytes)
    if not parse_result.resources:
        # The parser produced nothing at all. That's almost always a schema
        # problem (empty file, wrong file type, missing required columns).
        # We surface its error messages so the user knows what to fix.
        detail = "; ".join(parse_result.errors) or "no rows parsed"
        raise IngestionError(f"could not parse {filename!r}: {detail}")

    resources_dc = parse_result.resources
    findings_dc = run_engine(resources_dc)

    total_savings = round(sum(f.estimated_monthly_savings for f in findings_dc), 2)

    scan = Scan(
        source_filename=filename,
        provider=provider,
        resource_count=len(resources_dc),
        finding_count=len(findings_dc),
        total_monthly_savings=total_savings,
    )
    db.add(scan)
    db.flush()  # populate scan.id so FKs resolve below

    # One ORM Resource per parsed NormalizedResource, indexed by resource_id
    # so we can link Findings back without a second query.
    resource_orm_by_rid: dict[str, ResourceORM] = {}
    for resource in resources_dc:
        orm = ResourceORM(
            scan_id=scan.id,
            provider=resource.provider,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            region=resource.region,
            status=resource.status,
            monthly_cost=resource.monthly_cost,
            attached=resource.attached,
            last_activity_date=resource.last_activity_date,
            tags=resource.tags,
            raw=resource.raw,
        )
        db.add(orm)
        resource_orm_by_rid[resource.resource_id] = orm

    db.flush()  # populate resource.id values

    for finding in findings_dc:
        remediation = generate_remediation(finding)
        db.add(
            FindingORM(
                scan_id=scan.id,
                resource_pk=resource_orm_by_rid[finding.resource_id].id,
                rule_id=finding.rule_id,
                title=finding.title,
                reason=finding.reason,
                severity=finding.severity,
                estimated_monthly_savings=finding.estimated_monthly_savings,
                remediation_command=remediation.command,
            )
        )

    db.commit()
    db.refresh(scan)
    return scan
