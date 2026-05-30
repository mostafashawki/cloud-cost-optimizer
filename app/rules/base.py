"""Rule engine primitives — `Finding`, `Rule` Protocol, `REGISTRY`, `run_engine`.

Design goals (SPEC §5, T4 acceptance):

* **The engine is rule-agnostic.** `run_engine` iterates whatever is registered
  in `REGISTRY` and never references a specific `rule_id`. Adding a rule
  (T7 will add five) is a `catalog.py` edit only.
* **Rules are pure functions.** A rule maps `NormalizedResource -> Finding | None`;
  no I/O, no DB, no clock reads (rules that depend on "today" inject it as a
  parameter so they're testable — added in T7 for the date-threshold rules).
* **Finding is a value object.** This dataclass is the *in-memory* finding the
  engine produces; persistence happens in `services.run_scan()` (T6), which
  maps these onto the `app.models.Finding` ORM rows. Keeping them separate
  decouples the rule layer from SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.ingestion.normalize import NormalizedResource

Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class Finding:
    """A single detected source of waste."""

    rule_id: str
    resource_id: str
    resource_type: str
    provider: str
    region: str
    title: str
    reason: str
    severity: Severity
    estimated_monthly_savings: float
    # Populated by `app/remediation.py` in T5. Left as an empty string here so
    # the rule layer can stay completely ignorant of CLI command generation.
    remediation_command: str = ""


@runtime_checkable
class Rule(Protocol):
    """Anything that has the four metadata attributes and is callable on a
    `NormalizedResource` qualifies as a rule. Implemented as simple classes in
    `app/rules/catalog.py`.
    """

    rule_id: str
    title: str
    severity: Severity

    def __call__(self, resource: NormalizedResource) -> Finding | None: ...


# Order is insertion order, which means catalog.py's registration order also
# fixes the output order — handy for stable test assertions.
REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    """Register a rule. Returns the rule so it can be used as a one-liner.

    Raises ValueError on a duplicate `rule_id` — silent override would be a
    nasty source of "why isn't my new rule firing?" bugs.
    """
    if rule.rule_id in REGISTRY:
        raise ValueError(f"duplicate rule_id: {rule.rule_id!r}")
    REGISTRY[rule.rule_id] = rule
    return rule


def run_engine(resources: Iterable[NormalizedResource]) -> list[Finding]:
    """Apply every registered rule to every resource; collect non-None findings.

    Implementation note: this loops resources outer, rules inner, so the
    output groups all findings for resource A before any for resource B. The
    opposite order would group by rule; both are valid, but resource-first
    matches what `services.run_scan()` wants when it attaches findings back
    to their persisted resource row.
    """
    findings: list[Finding] = []
    for resource in resources:
        for rule in REGISTRY.values():
            finding = rule(resource)
            if finding is not None:
                findings.append(finding)
    return findings
