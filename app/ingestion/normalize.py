"""Provider-agnostic normalized resource produced by parsers (SPEC §4).

Parsers in `app/ingestion/{aws_cur,azure}.py` map provider-specific billing /
inventory rows to this shape; the rule engine consumes only this type, so
adding a new provider is purely a parser concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Provider = Literal["aws", "azure"]


@dataclass(slots=True)
class NormalizedResource:
    provider: Provider
    resource_id: str
    resource_type: str
    region: str
    status: str
    monthly_cost: float
    attached: bool
    last_activity_date: date | None = None
    tags: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
