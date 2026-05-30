"""Concrete detection rules (SPEC §5).

Each rule is a small frozen+slotted dataclass implementing the `Rule` Protocol
from `app/rules/base.py`:

  * `rule_id`, `title`, `severity` as class-level defaults so the constructor
    is `MyRule()` and the registered instance reads as a value object.
  * `__call__(self, resource, *, today=None) -> Finding | None`.

Date-threshold rules (#2 stopped-EC2, #4 orphaned-snapshot, #6 deallocated-VM)
resolve `today` from the kwarg first, falling back to `date.today()`. Rules
without a date check accept the `today` kwarg and ignore it so the engine can
call them uniformly.

Savings are rounded to 2dp at the boundary (python-implementer skill).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.ingestion.normalize import NormalizedResource
from app.rules.base import Finding, Severity, register


def _age_in_days(resource: NormalizedResource, today: date | None) -> int | None:
    """Days between `last_activity_date` and `today`.

    Returns None when the resource has no last-activity date — date-threshold
    rules treat that as "can't determine age, don't flag" rather than raising.
    """
    if resource.last_activity_date is None:
        return None
    reference = today if today is not None else date.today()
    return (reference - resource.last_activity_date).days


# --------------------------------------------------------------------------- #
# SPEC §5 #1 — Unattached EBS volume
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AwsUnattachedEbsVolume:
    """An EBS volume in status='available' is detached and billing for storage
    while serving no workload. Severity high (cheap to delete, snapshot first
    if the operator wants a rollback)."""

    rule_id: str = "aws_unattached_ebs_volume"
    title: str = "Unattached EBS volume"
    severity: Severity = "high"

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None:
        del today  # this rule has no date threshold
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


# --------------------------------------------------------------------------- #
# SPEC §5 #2 — Idle stopped EC2 (stopped > 30 days)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AwsIdleStoppedEc2:
    """A stopped EC2 instance still bills for attached EBS storage. After a
    month idle it's almost certainly forgotten, not 'about to come back'.
    Medium severity because terminating destroys local state — operator may
    want to snapshot first."""

    rule_id: str = "aws_idle_stopped_ec2"
    title: str = "Idle stopped EC2 instance (stopped > 30 days)"
    severity: Severity = "medium"
    threshold_days: int = 30

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None:
        if not (
            resource.provider == "aws"
            and resource.resource_type == "ec2_instance"
            and resource.status == "stopped"
        ):
            return None
        age = _age_in_days(resource, today)
        if age is None or age <= self.threshold_days:
            return None
        return Finding(
            rule_id=self.rule_id,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            provider=resource.provider,
            region=resource.region,
            title=self.title,
            reason=(
                f"EC2 instance {resource.resource_id} has been stopped for {age} days "
                f"(threshold {self.threshold_days})."
            ),
            severity=self.severity,
            estimated_monthly_savings=round(resource.monthly_cost, 2),
        )


# --------------------------------------------------------------------------- #
# SPEC §5 #3 — Unassociated Elastic IP
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AwsUnassociatedElasticIp:
    """An EIP not attached to any running resource bills $0.005/hour ≈ $3.65/mo
    of pure waste. Severity high because releasing it is trivially safe — the
    waste is recurring."""

    rule_id: str = "aws_unassociated_elastic_ip"
    title: str = "Unassociated Elastic IP"
    severity: Severity = "high"

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None:
        del today
        if not (
            resource.provider == "aws"
            and resource.resource_type == "elastic_ip"
            and resource.status == "unassociated"
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
                f"Elastic IP {resource.resource_id} is unassociated and accruing "
                "idle-address charges."
            ),
            severity=self.severity,
            estimated_monthly_savings=round(resource.monthly_cost, 2),
        )


# --------------------------------------------------------------------------- #
# SPEC §5 #4 — Orphaned snapshot (attached=false & age > 90 days)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AwsOrphanedSnapshot:
    """A snapshot whose parent volume no longer exists (modelled as
    `attached=False` in the normalized resource) and which is old enough that
    it's almost certainly a forgotten backup, not an active checkpoint. Low
    severity because snapshots are individually cheap, but they accumulate."""

    rule_id: str = "aws_orphaned_snapshot"
    title: str = "Orphaned EBS snapshot (age > 90 days, no parent volume)"
    severity: Severity = "low"
    threshold_days: int = 90

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None:
        if not (
            resource.provider == "aws"
            and resource.resource_type == "ebs_snapshot"
            and resource.attached is False
        ):
            return None
        age = _age_in_days(resource, today)
        if age is None or age <= self.threshold_days:
            return None
        return Finding(
            rule_id=self.rule_id,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            provider=resource.provider,
            region=resource.region,
            title=self.title,
            reason=(
                f"Snapshot {resource.resource_id} has no parent volume and is "
                f"{age} days old (threshold {self.threshold_days})."
            ),
            severity=self.severity,
            estimated_monthly_savings=round(resource.monthly_cost, 2),
        )


# --------------------------------------------------------------------------- #
# SPEC §5 #5 — Unattached Azure managed disk
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AzureUnattachedManagedDisk:
    """An Azure managed disk in status='unattached' is the Azure analogue of
    the AWS R1 case — pure storage waste with no attached VM."""

    rule_id: str = "azure_unattached_managed_disk"
    title: str = "Unattached Azure managed disk"
    severity: Severity = "high"

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None:
        del today
        if not (
            resource.provider == "azure"
            and resource.resource_type == "managed_disk"
            and resource.status == "unattached"
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
                f"Managed disk {resource.resource_id} is in status='unattached' "
                "and accruing storage cost."
            ),
            severity=self.severity,
            estimated_monthly_savings=round(resource.monthly_cost, 2),
        )


# --------------------------------------------------------------------------- #
# SPEC §5 #6 — Long-deallocated Azure VM (deallocated > 30 days)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AzureDeallocatedVm:
    """An Azure VM in status='deallocated' still bills for its OS disk and
    any attached data disks. After 30+ days it's the moral equivalent of a
    stopped EC2 instance from AWS R2."""

    rule_id: str = "azure_deallocated_vm"
    title: str = "Long-deallocated Azure VM (deallocated > 30 days)"
    severity: Severity = "medium"
    threshold_days: int = 30

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None:
        if not (
            resource.provider == "azure"
            and resource.resource_type == "virtual_machine"
            and resource.status == "deallocated"
        ):
            return None
        age = _age_in_days(resource, today)
        if age is None or age <= self.threshold_days:
            return None
        return Finding(
            rule_id=self.rule_id,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            provider=resource.provider,
            region=resource.region,
            title=self.title,
            reason=(
                f"VM {resource.resource_id} has been deallocated for {age} days "
                f"(threshold {self.threshold_days})."
            ),
            severity=self.severity,
            estimated_monthly_savings=round(resource.monthly_cost, 2),
        )


# --------------------------------------------------------------------------- #
# Registration — one call per rule. Adding a new rule is a one-liner here.
# --------------------------------------------------------------------------- #

register(AwsUnattachedEbsVolume())
register(AwsIdleStoppedEc2())
register(AwsUnassociatedElasticIp())
register(AwsOrphanedSnapshot())
register(AzureUnattachedManagedDisk())
register(AzureDeallocatedVm())
