"""Azure billing export (CSV) parser.

Maps each row to a `NormalizedResource`. Cost is read from
`CostInBillingCurrency` (NOT `Quantity`). Resource *state* — same
caveat as the AWS parser — travels in the extended
`ResourceType` / `ResourceStatus` / `Attached` / `LastActivityDate` columns
that `data/generate_samples.py` writes; in real exports it would come from
an Azure resource-graph snapshot.

Tag column is `Tags`, formatted `key1:value1;key2:value2` (the colon-separated
form is Azure's portal-export convention; the AWS sample uses `=` instead).
Malformed rows are counted and skipped, never raised.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import IO

from app.ingestion._parsing import (
    ParseResult,
    check_required_columns,
    open_text,
    parse_bool,
    parse_kv_pairs,
    parse_optional_date,
)
from app.ingestion.normalize import NormalizedResource

log = logging.getLogger(__name__)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "ResourceId",
    "CostInBillingCurrency",
    "ResourceLocation",
    "ResourceType",
    "ResourceStatus",
    "Attached",
)


def parse(source: str | bytes | Path | IO[str]) -> ParseResult:
    """Parse an Azure billing export CSV into a `ParseResult`."""
    stream = open_text(source)
    reader = csv.DictReader(stream)

    schema_error = check_required_columns(reader.fieldnames, REQUIRED_COLUMNS)
    if schema_error is not None:
        return schema_error

    resources: list[NormalizedResource] = []
    malformed_count = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        try:
            resource_id = (row["ResourceId"] or "").strip()
            if not resource_id:
                raise ValueError("empty ResourceId")

            cost_raw = (row["CostInBillingCurrency"] or "").strip()
            monthly_cost = float(cost_raw) if cost_raw else 0.0

            resources.append(
                NormalizedResource(
                    provider="azure",
                    resource_id=resource_id,
                    resource_type=row["ResourceType"].strip(),
                    region=row["ResourceLocation"].strip(),
                    status=row["ResourceStatus"].strip(),
                    monthly_cost=monthly_cost,
                    attached=parse_bool(row["Attached"]),
                    last_activity_date=parse_optional_date(row.get("LastActivityDate")),
                    tags=parse_kv_pairs(row.get("Tags"), kv_sep=":"),
                    raw=dict(row),
                )
            )
        except (ValueError, KeyError) as exc:
            malformed_count += 1
            message = f"row {row_num}: {exc}"
            errors.append(message)
            log.warning("azure parser skipped malformed row: %s", message)

    return ParseResult(
        resources=resources,
        malformed_count=malformed_count,
        errors=errors,
    )
