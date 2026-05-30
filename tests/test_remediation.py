"""Tests for `app/remediation.py`.

Per the playbook:
- one parametrized assertion per rule_id checking exact string equality
  (incl. flags / ids / region), starting with EBS — covered here for ALL
  six SPEC §5 rules so T7 doesn't need to touch this file
- source-inspection test asserting no boto3 / botocore / azure / subprocess
  import (via AST parse, not substring grep — the word 'Azure' appears in
  docstrings and we don't want to fail on that)

Plus:
- destructive flag is set correctly per rule (terminate-instances + vm delete
  are destructive; the other four are not)
- unknown rule_id raises KeyError with a useful message
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app import remediation
from app.rules.base import Finding


def _make_finding(*, rule_id: str, resource_id: str, region: str) -> Finding:
    return Finding(
        rule_id=rule_id,
        resource_id=resource_id,
        resource_type="placeholder",
        provider="aws",
        region=region,
        title="placeholder title",
        reason="placeholder reason",
        severity="high",
        estimated_monthly_savings=10.00,
    )


# --------------------------------------------------------------------------- #
# Per-rule exact-string templates (SPEC §5)
# --------------------------------------------------------------------------- #


REMEDIATION_CASES = [
    pytest.param(
        "aws_unattached_ebs_volume",
        "vol-0unattachedebs00001",
        "us-east-1",
        "aws ec2 delete-volume --volume-id vol-0unattachedebs00001 --region us-east-1",
        False,
        id="aws_unattached_ebs_volume",
    ),
    pytest.param(
        "aws_idle_stopped_ec2",
        "i-0longstoppedec2001",
        "us-east-1",
        "aws ec2 terminate-instances --instance-ids i-0longstoppedec2001 --region us-east-1",
        True,
        id="aws_idle_stopped_ec2",
    ),
    pytest.param(
        "aws_unassociated_elastic_ip",
        "eipalloc-0unassociated001",
        "us-east-1",
        "aws ec2 release-address --allocation-id eipalloc-0unassociated001 --region us-east-1",
        False,
        id="aws_unassociated_elastic_ip",
    ),
    pytest.param(
        "aws_orphaned_snapshot",
        "snap-0orphanedsnap00001",
        "us-east-1",
        "aws ec2 delete-snapshot --snapshot-id snap-0orphanedsnap00001 --region us-east-1",
        False,
        id="aws_orphaned_snapshot",
    ),
    pytest.param(
        "azure_unattached_managed_disk",
        "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-x",
        "eastus",
        "az disk delete --ids /subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/disks/disk-x --yes",
        False,
        id="azure_unattached_managed_disk",
    ),
    pytest.param(
        "azure_deallocated_vm",
        "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-y",
        "eastus",
        "az vm delete --ids /subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-y --yes",
        True,
        id="azure_deallocated_vm",
    ),
]


@pytest.mark.parametrize("rule_id, resource_id, region, expected_command, expected_destructive", REMEDIATION_CASES)
def test_generated_command_equals_spec_template_exactly(
    rule_id: str,
    resource_id: str,
    region: str,
    expected_command: str,
    expected_destructive: bool,
) -> None:
    finding = _make_finding(rule_id=rule_id, resource_id=resource_id, region=region)

    result = remediation.generate(finding)

    assert result.command == expected_command
    assert result.is_destructive is expected_destructive


# --------------------------------------------------------------------------- #
# Error path
# --------------------------------------------------------------------------- #


def test_generate_raises_keyerror_for_unknown_rule_id() -> None:
    finding = _make_finding(rule_id="not_a_real_rule", resource_id="x", region="us-east-1")

    with pytest.raises(KeyError, match="not_a_real_rule"):
        remediation.generate(finding)


# --------------------------------------------------------------------------- #
# Coverage parity: every supported template corresponds to a tested case
# --------------------------------------------------------------------------- #


def test_every_template_is_covered_by_a_parametrized_case() -> None:
    covered = {case.id for case in REMEDIATION_CASES}

    assert covered == set(remediation.supported_rule_ids())


# --------------------------------------------------------------------------- #
# Safety: source must not import cloud SDKs or execution helpers
# --------------------------------------------------------------------------- #


FORBIDDEN_IMPORT_ROOTS = frozenset({"boto3", "botocore", "azure", "subprocess", "os.system"})


def test_remediation_module_imports_no_cloud_sdk_or_subprocess() -> None:
    """Parse `app/remediation.py` and assert no `import X` / `from X import ...`
    statement has a top-level module name in the forbidden set.

    AST parsing (instead of a substring grep) is necessary because the words
    'azure', 'boto3', and 'subprocess' all legitimately appear in this
    module's docstring as part of the safety contract being asserted.
    """
    source = Path(remediation.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    bad_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    bad_imports.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                bad_imports.append(f"from {node.module} import ...")

    assert not bad_imports, (
        f"app/remediation.py contains forbidden imports: {bad_imports}. "
        "This module must remain offline and SDK-free (see SPEC §1 + CLAUDE.md)."
    )
