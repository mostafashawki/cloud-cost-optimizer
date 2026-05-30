"""Shared utilities for the AWS / Azure CSV parsers.

Kept internal (leading underscore) — public callers should import the
provider-specific `parse(...)` functions and the public `ParseResult` from
the respective parser module.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import IO

from app.ingestion.normalize import NormalizedResource

# Tokens accepted as truthy in the extended state columns. Anything else
# parses to False (so a typo never silently flips a healthy resource into an
# "attached" one).
_TRUTHY: frozenset[str] = frozenset({"true", "1", "yes", "y", "t"})


@dataclass(slots=True)
class ParseResult:
    """Outcome of parsing one CSV.

    `resources` is the normalized list ready for the rule engine.
    `malformed_count` is the number of rows skipped due to bad data; details
    are appended to `errors` (one string per skipped row) so the caller can
    surface them without dragging in a logger dependency.
    """

    resources: list[NormalizedResource]
    malformed_count: int = 0
    errors: list[str] = field(default_factory=list)

    @classmethod
    def schema_error(cls, message: str) -> ParseResult:
        return cls(resources=[], malformed_count=0, errors=[message])


def open_text(source: str | bytes | Path | IO[str]) -> IO[str]:
    """Normalize a heterogeneous source argument to a text stream.

    Accepts a path (str | Path), raw bytes (decoded as UTF-8), or an existing
    text stream — useful because FastAPI's `UploadFile` exposes both `.file`
    (binary stream) and `.read()` (bytes), and tests want to pass inline
    string CSVs through `io.StringIO`.
    """
    if isinstance(source, bytes):
        return io.StringIO(source.decode("utf-8"))
    if isinstance(source, str | Path):
        return io.StringIO(Path(source).read_text(encoding="utf-8"))
    return source


def parse_bool(value: str | None) -> bool:
    """Strict-ish boolean parse — only the canonical truthy tokens return True."""
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY


def parse_optional_date(value: str | None) -> date | None:
    """ISO-8601 date string -> `date`. Empty/None -> None.

    Raises `ValueError` on a non-empty, malformed value so the caller can count
    the row as malformed instead of silently swallowing bad data.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return date.fromisoformat(stripped)


def parse_kv_pairs(value: str | None, *, kv_sep: str, pair_sep: str = ";") -> dict[str, str]:
    """Generic tag-string parser.

    AWS sample uses `k=v;k=v`; Azure sample uses `k:v;k:v`. Same shape, just
    different separators — pass `kv_sep="="` or `kv_sep=":"`. Empty input
    yields an empty dict; malformed pairs are silently dropped (a single bad
    tag shouldn't poison the whole row).
    """
    if not value or not value.strip():
        return {}
    out: dict[str, str] = {}
    for pair in value.split(pair_sep):
        token = pair.strip()
        if not token or kv_sep not in token:
            continue
        key, _, val = token.partition(kv_sep)
        key = key.strip()
        if not key:
            continue
        out[key] = val.strip()
    return out


def check_required_columns(
    fieldnames: Iterable[str] | None,
    required: Iterable[str],
) -> ParseResult | None:
    """Return a schema-error ParseResult if the header is missing required
    columns, else None (caller proceeds with row iteration).
    """
    if fieldnames is None:
        return ParseResult.schema_error("empty file (no header row)")
    missing = set(required) - set(fieldnames)
    if missing:
        return ParseResult.schema_error(
            f"missing required columns: {sorted(missing)}"
        )
    return None
