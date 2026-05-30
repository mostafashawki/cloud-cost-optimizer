"""Concrete detection rules. Registered into `REGISTRY` via `base.register`.

T4 implements only SPEC §5 rule #1 (`aws_unattached_ebs_volume`); rules #2-#6
land in T7. Each rule is a small class that exposes the four metadata
attributes the `Rule` Protocol requires (`rule_id`, `title`, `severity`,
`__call__`).

The savings figure is the resource's `monthly_cost` rounded to two decimals
at the boundary — never store raw floats in JSON-bound output (python-
implementer skill).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.normalize import NormalizedResource
from app.rules.base import Finding, Severity, register


@dataclass(frozen=True, slots=True)
class AwsUnattachedEbsVolume:
    """SPEC §5 #1 — an EBS volume in `status="available"` is detached from any
    instance and is accruing storage cost for no work. Savings = full monthly
    cost; severity high (cheap to delete, easy to verify before deletion via
    a snapshot).
    """

    rule_id: str = "aws_unattached_ebs_volume"
    title: str = "Unattached EBS volume"
    severity: Severity = "high"

    def __call__(self, resource: NormalizedResource) -> Finding | None:
        if not (
            resource.provider == "aws"
            and resource.resource_type == "ebs_volume"
            and resource.status == "available"
        ):
            return None
        return Finding(
            rule_id=self.rule_id,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            provider=resource.provider,
            region=resource.region,
            title=self.title,
            reason=(
                f"EBS volume {resource.resource_id} is in status='available' "
                "(unattached) and accruing storage cost."
            ),
            severity=self.severity,
            estimated_monthly_savings=round(resource.monthly_cost, 2),
        )


# Single registration call — the engine in base.py picks this up automatically.
register(AwsUnattachedEbsVolume())
