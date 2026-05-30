"""Tests for the rule engine + every rule in `app/rules/catalog.py`.

Each rule gets a positive case (its planted orphan, exact savings + severity)
and a negative case (a near-miss that should NOT fire — wrong status, wrong
type, wrong provider, or age below threshold) via `pytest.mark.parametrize`.

Plus:
- the engine source contains no hard-coded `rule_id` (T4 acceptance:
  "adding a rule requires no engine change")
- every rule registers exactly once and exposes the four metadata attributes
- end-to-end: parsing the *real* `data/sample_*.csv` files and running the
  engine yields exactly six findings totalling $90.91 — one per rule, on the
  expected planted orphan IDs (T7 acceptance)
"""

from __future__ import annotations

import inspect
from datetime import date, timedelta
from pathlib import Path

import pytest

import app.rules.catalog  # noqa: F401  (import for side-effect: rule registration)
from app.ingestion.normalize import NormalizedResource
from app.rules import base as rules_base
from app.rules.base import REGISTRY, Finding, Rule, run_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_AWS = PROJECT_ROOT / "data" / "sample_aws_cur.csv"
SAMPLE_AZURE = PROJECT_ROOT / "data" / "sample_azure.csv"

# Pinned reference date matches `data/generate_samples.py:TODAY` so the
# age-threshold tests evaluate the same dates the sample data was generated
# against — fully deterministic, regardless of when the suite runs.
TODAY = date(2026, 5, 30)

EXPECTED_RULE_IDS: frozenset[str] = frozenset(
    {
        "aws_unattached_ebs_volume",
        "aws_idle_stopped_ec2",
        "aws_unassociated_elastic_ip",
        "aws_orphaned_snapshot",
        "azure_unattached_managed_disk",
        "azure_deallocated_vm",
    }
)


# --------------------------------------------------------------------------- #
# Constructors for synthetic resources used in the parametrized tests
# --------------------------------------------------------------------------- #


def _aws(
    *,
    resource_id: str,
    resource_type: str,
    status: str,
    attached: bool,
    monthly_cost: float,
    last_activity_date: date | None = None,
) -> NormalizedResource:
    return NormalizedResource(
        provider="aws",
        resource_id=resource_id,
        resource_type=resource_type,
        region="us-east-1",
        status=status,
        monthly_cost=monthly_cost,
        attached=attached,
        last_activity_date=last_activity_date,
    )


def _azure(
    *,
    resource_id: str,
    resource_type: str,
    status: str,
    attached: bool,
    monthly_cost: float,
    last_activity_date: date | None = None,
) -> NormalizedResource:
    return NormalizedResource(
        provider="azure",
        resource_id=resource_id,
        resource_type=resource_type,
        region="eastus",
        status=status,
        monthly_cost=monthly_cost,
        attached=attached,
        last_activity_date=last_activity_date,
    )


# --------------------------------------------------------------------------- #
# Engine / registry contract
# --------------------------------------------------------------------------- #


def test_all_six_rules_are_registered_with_expected_metadata() -> None:
    assert set(REGISTRY.keys()) == EXPECTED_RULE_IDS
    for rule_id, rule in REGISTRY.items():
        assert isinstance(rule, Rule), f"{rule_id} does not satisfy the Rule Protocol"
        assert rule.rule_id == rule_id
        assert rule.severity in {"low", "medium", "high"}
        assert isinstance(rule.title, str) and rule.title


def test_engine_returns_no_findings_for_empty_input() -> None:
    assert run_engine([], today=TODAY) == []


def test_engine_source_references_no_specific_rule_id() -> None:
    """T4 acceptance ('adding a rule requires no engine change') — still
    true after T7 added five rules. Engine source must remain unchanged in
    its reference to rule_ids (none)."""
    engine_source = inspect.getsource(rules_base)

    for slug in EXPECTED_RULE_IDS:
        assert slug not in engine_source, (
            f"engine source mentions specific rule {slug!r}; engine must stay rule-agnostic"
        )


# --------------------------------------------------------------------------- #
# Per-rule positive case — the orphan IS flagged, with expected severity + savings
# --------------------------------------------------------------------------- #


ORPHAN_CASES = [
    pytest.param(
        "aws_unattached_ebs_volume",
        _aws(
            resource_id="vol-x",
            resource_type="ebs_volume",
            status="available",
            attached=False,
            monthly_cost=12.00,
        ),
        "high",
        12.00,
        id="aws_unattached_ebs_volume",
    ),
    pytest.param(
        "aws_idle_stopped_ec2",
        _aws(
            resource_id="i-x",
            resource_type="ec2_instance",
            status="stopped",
            attached=True,
            monthly_cost=25.00,
            last_activity_date=TODAY - timedelta(days=80),
        ),
        "medium",
        25.00,
        id="aws_idle_stopped_ec2",
    ),
    pytest.param(
        "aws_unassociated_elastic_ip",
        _aws(
            resource_id="eipalloc-x",
            resource_type="elastic_ip",
            status="unassociated",
            attached=False,
            monthly_cost=3.65,
        ),
        "high",
        3.65,
        id="aws_unassociated_elastic_ip",
    ),
    pytest.param(
        "aws_orphaned_snapshot",
        _aws(
            resource_id="snap-x",
            resource_type="ebs_snapshot",
            status="completed",
            attached=False,
            monthly_cost=2.50,
            last_activity_date=TODAY - timedelta(days=150),
        ),
        "low",
        2.50,
        id="aws_orphaned_snapshot",
    ),
    pytest.param(
        "azure_unattached_managed_disk",
        _azure(
            resource_id="/sub/abc/.../disks/disk-x",
            resource_type="managed_disk",
            status="unattached",
            attached=False,
            monthly_cost=5.76,
        ),
        "high",
        5.76,
        id="azure_unattached_managed_disk",
    ),
    pytest.param(
        "azure_deallocated_vm",
        _azure(
            resource_id="/sub/abc/.../vms/vm-x",
            resource_type="virtual_machine",
            status="deallocated",
            attached=True,
            monthly_cost=42.00,
            last_activity_date=TODAY - timedelta(days=60),
        ),
        "medium",
        42.00,
        id="azure_deallocated_vm",
    ),
]


@pytest.mark.parametrize("rule_id, orphan, severity, savings", ORPHAN_CASES)
def test_rule_fires_on_orphan_with_expected_severity_and_savings(
    rule_id: str,
    orphan: NormalizedResource,
    severity: str,
    savings: float,
) -> None:
    findings = run_engine([orphan], today=TODAY)

    matching = [f for f in findings if f.rule_id == rule_id]
    assert len(matching) == 1, (
        f"rule {rule_id} did not fire on its orphan (got {[f.rule_id for f in findings]})"
    )
    finding = matching[0]
    assert isinstance(finding, Finding)
    assert finding.severity == severity
    assert finding.estimated_monthly_savings == pytest.approx(savings)
    assert finding.resource_id == orphan.resource_id
    assert finding.provider == orphan.provider
    assert finding.region == orphan.region


# --------------------------------------------------------------------------- #
# Per-rule negative case — a near-miss must NOT fire
# --------------------------------------------------------------------------- #


HEALTHY_CASES = [
    pytest.param(
        "aws_unattached_ebs_volume",
        _aws(
            resource_id="vol-healthy",
            resource_type="ebs_volume",
            status="in-use",  # attached, in service
            attached=True,
            monthly_cost=8.00,
        ),
        id="aws_unattached_ebs_volume",
    ),
    pytest.param(
        "aws_idle_stopped_ec2",
        # Stopped — but only 5 days ago, well under the 30-day threshold.
        _aws(
            resource_id="i-recent",
            resource_type="ec2_instance",
            status="stopped",
            attached=True,
            monthly_cost=25.00,
            last_activity_date=TODAY - timedelta(days=5),
        ),
        id="aws_idle_stopped_ec2",
    ),
    pytest.param(
        "aws_unassociated_elastic_ip",
        _aws(
            resource_id="eipalloc-attached",
            resource_type="elastic_ip",
            status="associated",
            attached=True,
            monthly_cost=0.00,
        ),
        id="aws_unassociated_elastic_ip",
    ),
    pytest.param(
        "aws_orphaned_snapshot",
        # 120d old but `attached=True` (parent volume still exists).
        _aws(
            resource_id="snap-attached",
            resource_type="ebs_snapshot",
            status="completed",
            attached=True,
            monthly_cost=2.50,
            last_activity_date=TODAY - timedelta(days=120),
        ),
        id="aws_orphaned_snapshot",
    ),
    pytest.param(
        "azure_unattached_managed_disk",
        _azure(
            resource_id="/sub/abc/.../disks/disk-healthy",
            resource_type="managed_disk",
            status="attached",
            attached=True,
            monthly_cost=8.00,
        ),
        id="azure_unattached_managed_disk",
    ),
    pytest.param(
        "azure_deallocated_vm",
        # Deallocated 10 days ago — below the 30-day threshold.
        _azure(
            resource_id="/sub/abc/.../vms/vm-recent",
            resource_type="virtual_machine",
            status="deallocated",
            attached=True,
            monthly_cost=42.00,
            last_activity_date=TODAY - timedelta(days=10),
        ),
        id="azure_deallocated_vm",
    ),
]


@pytest.mark.parametrize("rule_id, healthy", HEALTHY_CASES)
def test_rule_does_not_fire_on_near_miss(
    rule_id: str,
    healthy: NormalizedResource,
) -> None:
    findings = run_engine([healthy], today=TODAY)

    matching = [f for f in findings if f.rule_id == rule_id]
    assert matching == [], f"rule {rule_id} unexpectedly fired on a near-miss resource"


# --------------------------------------------------------------------------- #
# Boundary: snapshot exactly at 90d should NOT fire (rule says STRICTLY > 90d)
# --------------------------------------------------------------------------- #


def test_snapshot_rule_is_strictly_greater_than_threshold() -> None:
    snapshot_exact = _aws(
        resource_id="snap-at-threshold",
        resource_type="ebs_snapshot",
        status="completed",
        attached=False,
        monthly_cost=2.50,
        last_activity_date=TODAY - timedelta(days=90),
    )
    snapshot_just_over = _aws(
        resource_id="snap-just-over",
        resource_type="ebs_snapshot",
        status="completed",
        attached=False,
        monthly_cost=2.50,
        last_activity_date=TODAY - timedelta(days=91),
    )

    findings_at = run_engine([snapshot_exact], today=TODAY)
    findings_over = run_engine([snapshot_just_over], today=TODAY)

    assert findings_at == []
    assert len(findings_over) == 1
    assert findings_over[0].rule_id == "aws_orphaned_snapshot"


# --------------------------------------------------------------------------- #
# Missing last_activity_date for a date-threshold rule -> don't fire
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "rule_id, resource",
    [
        (
            "aws_idle_stopped_ec2",
            _aws(
                resource_id="i-no-date",
                resource_type="ec2_instance",
                status="stopped",
                attached=True,
                monthly_cost=25.00,
                last_activity_date=None,
            ),
        ),
        (
            "aws_orphaned_snapshot",
            _aws(
                resource_id="snap-no-date",
                resource_type="ebs_snapshot",
                status="completed",
                attached=False,
                monthly_cost=2.50,
                last_activity_date=None,
            ),
        ),
        (
            "azure_deallocated_vm",
            _azure(
                resource_id="/.../vms/vm-no-date",
                resource_type="virtual_machine",
                status="deallocated",
                attached=True,
                monthly_cost=42.00,
                last_activity_date=None,
            ),
        ),
    ],
)
def test_date_threshold_rule_does_not_fire_when_last_activity_is_missing(
    rule_id: str,
    resource: NormalizedResource,
) -> None:
    findings = run_engine([resource], today=TODAY)
    assert not any(f.rule_id == rule_id for f in findings)


# --------------------------------------------------------------------------- #
# End-to-end on the real sample data (T7 acceptance)
# --------------------------------------------------------------------------- #


def test_every_rule_fires_exactly_once_on_its_seeded_orphan_in_sample_data() -> None:
    from app.ingestion import aws_cur
    from app.ingestion import azure as azure_parser

    aws_resources = aws_cur.parse(SAMPLE_AWS).resources
    az_resources = azure_parser.parse(SAMPLE_AZURE).resources

    findings = run_engine([*aws_resources, *az_resources], today=TODAY)

    by_rule_id = {f.rule_id: f for f in findings}

    # Each rule fires exactly once on its planted orphan.
    assert len(findings) == 6
    assert set(by_rule_id) == EXPECTED_RULE_IDS

    # Exact resource-id matches per data/EXPECTED.md.
    assert by_rule_id["aws_unattached_ebs_volume"].resource_id == "vol-0unattachedebs00001"
    assert by_rule_id["aws_idle_stopped_ec2"].resource_id == "i-0longstoppedec2001"
    assert by_rule_id["aws_unassociated_elastic_ip"].resource_id == "eipalloc-0unassociated001"
    assert by_rule_id["aws_orphaned_snapshot"].resource_id == "snap-0orphanedsnap00001"
    assert by_rule_id["azure_unattached_managed_disk"].resource_id.endswith(
        "/disk-unattached-demo-001"
    )
    assert by_rule_id["azure_deallocated_vm"].resource_id.endswith("/vm-deallocated-demo-001")


def test_total_savings_across_all_rules_matches_expected_grand_total() -> None:
    from app.ingestion import aws_cur
    from app.ingestion import azure as azure_parser

    aws_resources = aws_cur.parse(SAMPLE_AWS).resources
    az_resources = azure_parser.parse(SAMPLE_AZURE).resources

    findings = run_engine([*aws_resources, *az_resources], today=TODAY)

    total = sum(f.estimated_monthly_savings for f in findings)

    # Grand total per data/EXPECTED.md.
    assert total == pytest.approx(90.91, abs=0.01)
