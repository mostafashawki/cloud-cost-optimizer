"""AWS Cost & Usage Report (CSV) parser.

Maps each row to a `NormalizedResource`. Cost is read from
`lineItem/UnblendedCost` (NOT `lineItem/UsageAmount`, which is the
quantity/usage figure — using usage as cost is a classic bug the
finops-domain skill explicitly warns against).

Resource *state* (status / attached / last_activity_date) is read from the
extended `resource/*` columns introduced by `data/generate_samples.py`. In
real CUR data this state would come from joining the billing rows with an
inventory snapshot (`aws ec2 describe-volumes` et al.); for this offline MVP
the state travels alongside the cost in a single CSV.

Malformed rows (bad cost, bad date, empty resource id) are counted and
skipped — never raised — so a single bad line can't sink an entire upload.
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
    "lineItem/ResourceId",
    "lineItem/UnblendedCost",
    "product/region",
    "resource/type",
    "resource/status",
    "resource/attached",
)


def parse(source: str | bytes | Path | IO[str]) -> ParseResult:
    """Parse an AWS CUR CSV into a `ParseResult`."""
    stream = open_text(source)
    reader = csv.DictReader(stream)

    schema_error = check_required_columns(reader.fieldnames, REQUIRED_COLUMNS)
    if schema_error is not None:
        return schema_error

    resources: list[NormalizedResource] = []
    malformed_count = 0
    errors: list[str] = []

    # `start=2` because row 1 is the header; this gives users 1-based row
    # numbers in error messages that match what they see in a spreadsheet.
    for row_num, row in enumerate(reader, start=2):
        try:
            resource_id = (row["lineItem/ResourceId"] or "").strip()
            if not resource_id:
                raise ValueError("empty lineItem/ResourceId")

            cost_raw = (row["lineItem/UnblendedCost"] or "").strip()
            monthly_cost = float(cost_raw) if cost_raw else 0.0

            resources.append(
                NormalizedResource(
                    provider="aws",
                    resource_id=resource_id,
                    resource_type=row["resource/type"].strip(),
                    region=row["product/region"].strip(),
                    status=row["resource/status"].strip(),
                    monthly_cost=monthly_cost,
                    attached=parse_bool(row["resource/attached"]),
                    last_activity_date=parse_optional_date(
                        row.get("resource/last_activity_date")
                    ),
                    tags=parse_kv_pairs(row.get("resource/tags"), kv_sep="="),
                    raw=dict(row),
                )
            )
        except (ValueError, KeyError) as exc:
            malformed_count += 1
            message = f"row {row_num}: {exc}"
            errors.append(message)
            log.warning("aws_cur parser skipped malformed row: %s", message)

    return ParseResult(
        resources=resources,
        malformed_count=malformed_count,
        errors=errors,
    )
