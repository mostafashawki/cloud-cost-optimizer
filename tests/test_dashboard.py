"""Smoke test for the dashboard (SPEC §7, T8).

GET / must return the single-file dashboard with every element ID the JS
targets and the API endpoints the JS calls. We don't run a browser here;
this catches "I deleted an id by mistake" / "I broke the route" regressions.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

# Element IDs the inline JS reads / writes. If any is renamed in
# `static/index.html` without updating the JS, the dashboard silently breaks;
# this test makes that visible.
REQUIRED_ELEMENT_IDS: tuple[str, ...] = (
    "scan-form",
    "file-input",
    "provider-select",
    "scan-button",
    "status-message",
    "error-message",
    "empty-state",
    "results-section",
    "kpi-total-savings",
    "kpi-finding-count",
    "kpi-high-count",
    "savings-chart",
    "findings-table",
    "findings-tbody",
)

# Endpoint paths the dashboard's fetch() calls must reference verbatim.
REQUIRED_ENDPOINTS: tuple[str, ...] = (
    "/scans",
    "/summary",
    "/findings",
)


def test_dashboard_route_returns_html_with_200(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("text/html"), content_type


def test_dashboard_html_contains_every_element_the_js_targets(
    client: TestClient,
) -> None:
    response = client.get("/")
    assert response.status_code == 200

    body = response.text
    for element_id in REQUIRED_ELEMENT_IDS:
        assert f'id="{element_id}"' in body, (
            f'missing element id={element_id!r} — the JS will silently fail '
            "until you restore it"
        )


def test_dashboard_html_references_the_api_endpoints(client: TestClient) -> None:
    body = client.get("/").text

    for endpoint in REQUIRED_ENDPOINTS:
        assert endpoint in body, f"dashboard JS no longer references {endpoint!r}"


def test_dashboard_html_loads_chart_js_from_cdn(client: TestClient) -> None:
    body = client.get("/").text

    # Must be a real CDN URL, not a relative path (we have no /static mount
    # and the project ships no vendored copy).
    assert "https://cdn.jsdelivr.net/npm/chart.js" in body
