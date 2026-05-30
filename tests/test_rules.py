"""Tests for the rule engine + T4's single rule (`aws_unattached_ebs_volume`).

Required by the playbook:
- positive: unattached volume flagged, severity high, savings correct
- negative: in-use volume NOT flagged

Plus a few non-negotiables for the *engine* itself:
- iterating an empty resource list returns no findings (no rule errors out)
- the engine source contains no hard-coded `rule_id` (acceptance criterion:
  "adding a rule requires no engine change")
- the rule is reachable via the public REGISTRY
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

# Importing the catalog has the side-effect of registering rules; tests touch
# `REGISTRY` indirectly via `run_engine`, so we import the catalog explicitly
# to make that dependency visible.
import app.rules.catalog  # noqa: F401  (import for side-effect: rule registration)
from app.ingestion.normalize import NormalizedResource
from app.rules import base as rules_base
from app.rules.base import REGISTRY, Finding, Rule, run_engine


def _ebs(*, resource_id: str, status: str, attached: bool, monthly_cost: float) -> NormalizedResource:
    return NormalizedResource(
        provider="aws",
        resource_id=resource_id,
        resource_type="ebs_volume",
        region="us-east-1",
        status=status,
        monthly_cost=monthly_cost,
        attached=attached,
        last_activity_date=date(2026, 5, 1),
    )


# --------------------------------------------------------------------------- #
# Engine / registry contract
# --------------------------------------------------------------------------- #


def test_aws_unattached_ebs_volume_rule_is_registered() -> None:
    assert "aws_unattached_ebs_volume" in REGISTRY
    rule = REGISTRY["aws_unattached_ebs_volume"]
    assert isinstance(rule, Rule)
    assert rule.severity == "high"
    assert rule.title == "Unattached EBS volume"


def test_engine_returns_no_findings_for_empty_input() -> None:
    assert run_engine([]) == []


def test_engine_source_references_no_specific_rule_id() -> None:
    """T4 acceptance: 'adding a rule requires no engine change'.

    The engine should iterate `REGISTRY` and have no hard-coded knowledge of
    any particular rule. We assert that by reading the engine source and
    checking that no `rule_id` slug appears literally inside it.
    """
    engine_source = inspect.getsource(rules_base)

    # Sanity check: there is at least one rule we expect not to find named.
    expected_to_be_absent = ["aws_unattached_ebs_volume", "azure_unattached_managed_disk"]
    for slug in expected_to_be_absent:
        assert slug not in engine_source, (
            f"engine source mentions specific rule {slug!r}; engine must stay rule-agnostic"
        )


# --------------------------------------------------------------------------- #
# Positive case (the rule's job)
# --------------------------------------------------------------------------- #


def test_unattached_ebs_volume_is_flagged_with_severity_high_and_correct_savings() -> None:
    orphan = _ebs(
        resource_id="vol-0unattachedebs00001",
        status="available",
        attached=False,
        monthly_cost=12.00,
    )

    findings = run_engine([orphan])

    assert len(findings) == 1
    finding = findings[0]
    assert isinstance(finding, Finding)
    assert finding.rule_id == "aws_unattached_ebs_volume"
    assert finding.severity == "high"
    assert finding.estimated_monthly_savings == pytest.approx(12.00)
    assert finding.resource_id == "vol-0unattachedebs00001"
    assert finding.resource_type == "ebs_volume"
    assert finding.provider == "aws"
    assert finding.region == "us-east-1"
    assert finding.title == "Unattached EBS volume"
    assert "vol-0unattachedebs00001" in finding.reason
    assert "available" in finding.reason
    # T5 will populate this. For now, must be the empty default.
    assert finding.remediation_command == ""


def test_savings_are_rounded_to_two_decimals_at_the_boundary() -> None:
    odd = _ebs(
        resource_id="vol-0odd",
        status="available",
        attached=False,
        monthly_cost=9.123456,
    )

    findings = run_engine([odd])

    assert findings[0].estimated_monthly_savings == pytest.approx(9.12)


# --------------------------------------------------------------------------- #
# Negative case (rule must NOT flag healthy resources)
# --------------------------------------------------------------------------- #


def test_in_use_ebs_volume_is_not_flagged() -> None:
    healthy = _ebs(
        resource_id="vol-0healthy",
        status="in-use",
        attached=True,
        monthly_cost=8.00,
    )

    findings = run_engine([healthy])

    assert findings == []


def test_volume_in_other_provider_is_not_flagged() -> None:
    not_aws = NormalizedResource(
        provider="azure",
        resource_id="something",
        resource_type="ebs_volume",  # nonsensical for azure, but tests provider check
        region="eastus",
        status="available",
        monthly_cost=12.00,
        attached=False,
    )

    assert run_engine([not_aws]) == []


def test_non_ebs_resource_is_not_flagged() -> None:
    not_ebs = NormalizedResource(
        provider="aws",
        resource_id="i-0xyz",
        resource_type="ec2_instance",
        region="us-east-1",
        status="available",  # nonsensical, tests resource_type gate
        monthly_cost=20.00,
        attached=False,
    )

    assert run_engine([not_ebs]) == []


# --------------------------------------------------------------------------- #
# Engine handles multiple resources (orphan + healthy mixed)
# --------------------------------------------------------------------------- #


def test_engine_flags_only_the_orphans_in_a_mixed_input() -> None:
    orphan = _ebs(resource_id="vol-orphan", status="available", attached=False, monthly_cost=10.0)
    healthy = _ebs(resource_id="vol-healthy", status="in-use", attached=True, monthly_cost=8.0)

    findings = run_engine([healthy, orphan, healthy])

    assert len(findings) == 1
    assert findings[0].resource_id == "vol-orphan"
