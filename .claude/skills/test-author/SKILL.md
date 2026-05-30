---
name: test-author
description: "Use when writing the pytest suite for any task. Defines test structure, fixtures, naming, the FastAPI TestClient pattern, and how to assert deterministically against the planted orphans in the sample data. Every task in PLAN.md names its Required tests — this skill says how to write them well."
---

# Test Author

Tests are the acceptance gate. They must be deterministic and tied to known expected values.

## Conventions
- `pytest`; tests in `tests/`, files `test_*.py`, functions `test_<unit>_<condition>_<expected>`.
- Arrange-Act-Assert, one behavior per test. No network, no randomness, no real cloud.
- Fixtures in `tests/conftest.py`: a `client` fixture returning a `TestClient(app)` over a
  **temporary SQLite file** (or in-memory) so tests are isolated and the real `data/app.db` is never
  touched; a `sample_data` fixture that points at the committed `sample/` files (or regenerates them
  with the seeded generator).
- API tests use `httpx`/`starlette` `TestClient`; assert status code AND response body.

## Asserting against planted data
`sample/EXPECTED.md` is the contract for what the generator planted (e.g. 3 unattached volumes,
2 idle EIPs, 1 long-stopped instance, 2 orphaned snapshots, and N clean resources). Tests assert
exact numbers, not "greater than zero":
- detection: each rule returns exactly its planted count; `test_no_findings_for_clean_resources`
  asserts the clean fixtures produce zero findings (guards against false positives).
- savings: `test_detection_total_savings_matches_expected` asserts the summed savings equals the
  documented expected total (within 0.01 for float rounding).
- e2e: ingest → `/analyze` → `/summary` returns the same planted totals through the API.

## Coverage to insist on per layer
- Parsers: happy path + malformed input rejected (400/422) + unknown provider rejected.
- Detection: each rule's positive case, each rule's negative/clean case, and the aggregate total.
- Remediation: correct command string per rule; destructive commented without `confirm`, active with
  `confirm`; a source-inspection test asserting `app/remediate.py` imports no `boto3`/`botocore`/
  `azure`/`subprocess` (read the file text and assert those tokens are absent from imports).
- API: every endpoint's success path + at least one failure path; filters on `/findings`.
- Dashboard: `GET /` returns 200 + `text/html`; body references the summary endpoint.

## Quality bar
A test must fail if the behavior regresses. When fixing a bug, first add a test that reproduces it
(red), then fix (green). Keep the suite fast (< a few seconds) so it can run after every task.
