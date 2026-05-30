"""Generate decommission CLI command strings from `Finding`s.

Safety contract (SPEC §1 + CLAUDE.md non-negotiables + finops-domain skill):
- This module imports NO cloud SDK (no `boto3`, no `botocore`, no `azure-*`).
- This module executes NOTHING (no `subprocess`, no `os.system`).
- It only constructs string templates. Any execution is the operator's
  problem, by design — running the commands is explicitly out of scope.

`tests/test_remediation.py` asserts the absence of those imports via AST
inspection, so a refactor can't quietly add `import boto3` without the suite
going red.

Templates are the verbatim ones in SPEC §5; the dict below is the single
source of truth for both the command string and the destructiveness flag.
Adding a new rule in T7 only requires registering it in
`app/rules/catalog.py` AND adding a new entry to `_TEMPLATES` here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.rules.base import Finding


@dataclass(frozen=True, slots=True)
class RemediationCommand:
    """The shell command that would decommission the wasted resource.

    `is_destructive` flags commands that delete potentially-restartable
    compute (a stopped EC2 / a deallocated VM) — i.e. the operator may want
    a snapshot or a confirmation step before running them. Deletes of
    already-orphaned objects (unattached disk / volume, unassociated EIP,
    orphaned snapshot) are NOT flagged destructive: there is no live workload
    they could disrupt.
    """

    command: str
    is_destructive: bool


@dataclass(frozen=True, slots=True)
class _Template:
    template: str
    is_destructive: bool


# Rule-id -> template (exact strings per SPEC §5). Format placeholders are
# {rid} for the resource id and {region} for the region. Azure templates
# don't use {region} (the resource id is a full ARM path that already
# encodes location); `.format(...)` silently ignores extra kwargs, so the
# single call site below works for both providers.
_TEMPLATES: dict[str, _Template] = {
    "aws_unattached_ebs_volume": _Template(
        template="aws ec2 delete-volume --volume-id {rid} --region {region}",
        is_destructive=False,
    ),
    "aws_idle_stopped_ec2": _Template(
        template="aws ec2 terminate-instances --instance-ids {rid} --region {region}",
        is_destructive=True,
    ),
    "aws_unassociated_elastic_ip": _Template(
        template="aws ec2 release-address --allocation-id {rid} --region {region}",
        is_destructive=False,
    ),
    "aws_orphaned_snapshot": _Template(
        template="aws ec2 delete-snapshot --snapshot-id {rid} --region {region}",
        is_destructive=False,
    ),
    "azure_unattached_managed_disk": _Template(
        template="az disk delete --ids {rid} --yes",
        is_destructive=False,
    ),
    "azure_deallocated_vm": _Template(
        template="az vm delete --ids {rid} --yes",
        is_destructive=True,
    ),
}


def generate(finding: Finding) -> RemediationCommand:
    """Build the CLI command for a finding.

    Raises `KeyError` for an unknown `rule_id` — that signals a rule was
    registered in the catalog without a corresponding template entry, which
    is a programmer error worth surfacing loudly rather than silently
    producing an empty string.
    """
    try:
        tpl = _TEMPLATES[finding.rule_id]
    except KeyError:
        raise KeyError(
            f"no remediation template for rule_id={finding.rule_id!r}"
        ) from None
    return RemediationCommand(
        command=tpl.template.format(rid=finding.resource_id, region=finding.region),
        is_destructive=tpl.is_destructive,
    )


def supported_rule_ids() -> frozenset[str]:
    """Set of rule_ids that have a remediation template. Useful for the
    catalog/template consistency test added in T7."""
    return frozenset(_TEMPLATES)
