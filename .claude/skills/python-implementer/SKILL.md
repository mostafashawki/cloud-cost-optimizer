---
name: python-implementer
description: "Use when writing or modifying application code in this repo (FastAPI endpoints, SQLAlchemy models/sessions, Pydantic schemas, parsers, the single-file dashboard). Defines the structural conventions, patterns, and quality bar for implementation work across all tasks."
---

# Python Implementer

How to write code here. The bar is "production MVP", not "script".

## Stack patterns
- **FastAPI**: app factory in `app/main.py` returning the configured app; routers live in `app/api/`
  and are included via `app.include_router(...)`. Use dependency injection for the DB session.
- **SQLAlchemy 2.0**: typed `Mapped[...]` / `mapped_column(...)` models; one `SessionLocal`; a
  `get_db()` generator dependency that yields and closes a session. `create_all` on startup.
- **Pydantic v2**: separate request and response models in `app/schemas.py`. Validate every external
  input (uploads, query params). Use `pydantic-settings` for config (`app/config.py`), never read
  env vars ad hoc.
- **Uploads**: `UploadFile` + `python-multipart`. Read, validate shape, parse, persist. Reject
  malformed input with `HTTPException(400/422)` and a message that says what was wrong — never let it
  reach a 500.

## Structure & style
- Small single-purpose functions. Detection rules (`app/detect.py`) are **pure**: data in, findings
  out, no DB or I/O — this is what makes them trivially testable. The API layer does the I/O and
  calls them.
- Full type hints everywhere. Run `ruff check . --fix` before declaring done; leave it clean.
- No bare `except`; catch specific exceptions. No `print` for control flow — use `logging`.
- Money as `Decimal` internally or rounded to 2dp at the boundary; never expose raw floats in JSON.
- No `TODO`/stub/placeholder in a task you're calling done. No secrets or real account IDs committed.
- Constants (unit prices, thresholds) are named with a source comment, never inline magic numbers.

## Dashboard (T7)
One `app/static/index.html`, served at `/` via `FileResponse` or a mounted static route. Vanilla JS,
Chart.js from a CDN `<script>`. No bundler, no framework, no build step. It only calls the JSON API
(`/summary`, `/findings`). Provide a clear empty state before any analysis has run. Keep it legible —
KPI cards, one bar chart, one table with a copy-to-clipboard button per command.

## Definition of done (implementation side)
Code matches the current task's acceptance criteria in `docs/PLAN.md`; types complete; `ruff` clean;
no dead code; the `test-author` skill's tests for this task exist and pass. Then hand off to
`code-reviewer`. If a later task needs a refactor, do it deliberately and keep all prior tests green.
