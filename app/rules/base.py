"""Rule engine primitives — `Finding`, `Rule` Protocol, `REGISTRY`, `run_engine`.

Design goals (SPEC §5, T4 + T7 acceptance):

* **The engine is rule-agnostic.** `run_engine` iterates whatever is registered
  in `REGISTRY` and never references a specific `rule_id`. Adding a rule is
  a `catalog.py` edit only.
* **Rules are pure functions of (resource, today).** `today` is injected
  (not read from the wall clock inside rules) so date-threshold logic is
  trivially testable — pass `today=date(...)` to `run_engine` and the rules
  evaluate against that anchor. In production, services.run_scan passes no
  `today` and each rule falls back to `date.today()`.
* **Finding is a value object.** This dataclass is the *in-memory* finding the
  engine produces; persistence happens in `services.run_scan()`, which maps
  these onto the `app.models.Finding` ORM rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
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
    remediation_command: str = ""


@runtime_checkable
class Rule(Protocol):
    """Anything with the four metadata attributes and a `(resource, today=)`
    callable qualifies as a rule. Implemented as small dataclasses in
    `app/rules/catalog.py`.
    """

    rule_id: str
    title: str
    severity: Severity

    def __call__(
        self,
        resource: NormalizedResource,
        *,
        today: date | None = None,
    ) -> Finding | None: ...


REGISTRY: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    """Register a rule. Raises ValueError on a duplicate `rule_id` so silent
    shadowing of a working rule by a copy-paste error fails loudly."""
    if rule.rule_id in REGISTRY:
        raise ValueError(f"duplicate rule_id: {rule.rule_id!r}")
    REGISTRY[rule.rule_id] = rule
    return rule


def run_engine(
    resources: Iterable[NormalizedResource],
    *,
    today: date | None = None,
) -> list[Finding]:
    """Apply every registered rule to every resource; collect non-None findings.

    `today` is forwarded to every rule. Pass `today=None` (default) to use the
    wall clock; pass an explicit date for deterministic tests.
    """
    findings: list[Finding] = []
    for resource in resources:
        for rule in REGISTRY.values():
            finding = rule(resource, today=today)
            if finding is not None:
                findings.append(finding)
    return findings
