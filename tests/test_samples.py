"""Tests for `data/generate_samples.py` — the planted-orphan contract.

These tests assert verbatim against `data/EXPECTED.md`: same orphan IDs, same
row counts, same dollar totals. If the generator is ever changed, EXPECTED.md
and every downstream rule/test must move in lock-step.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from data.generate_samples import write_samples

PLANTED_AWS_IDS: set[str] = {
    "vol-0unattachedebs00001",
    "i-0longstoppedec2001",
    "eipalloc-0unassociated001",
    "snap-0orphanedsnap00001",
}

PLANTED_AZURE_NAME_SUFFIXES: set[str] = {
    "disk-unattached-demo-001",
    "vm-deallocated-demo-001",
}

EXPECTED_AWS_ROW_COUNT = 8
EXPECTED_AZURE_ROW_COUNT = 4
EXPECTED_AWS_SUBTOTAL = 43.15
EXPECTED_AZURE_SUBTOTAL = 47.76
EXPECTED_TOTAL_MONTHLY_SAVINGS = 90.91


@pytest.fixture
def generated(tmp_path: Path) -> tuple[Path, Path]:
    aws = tmp_path / "sample_aws_cur.csv"
    azure = tmp_path / "sample_azure.csv"
    write_samples(aws, azure)
    return aws, azure


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_aws_sample_row_count_matches_expected(generated: tuple[Path, Path]) -> None:
    aws, _ = generated

    rows = _read_csv(aws)

    assert len(rows) == EXPECTED_AWS_ROW_COUNT


def test_azure_sample_row_count_matches_expected(generated: tuple[Path, Path]) -> None:
    _, azure = generated

    rows = _read_csv(azure)

    assert len(rows) == EXPECTED_AZURE_ROW_COUNT


def test_all_planted_aws_orphan_ids_are_present(generated: tuple[Path, Path]) -> None:
    aws, _ = generated

    seen_ids = {row["lineItem/ResourceId"] for row in _read_csv(aws)}

    missing = PLANTED_AWS_IDS - seen_ids
    assert not missing, f"Missing planted AWS orphan IDs: {missing}"


def test_all_planted_azure_orphan_ids_are_present(generated: tuple[Path, Path]) -> None:
    _, azure = generated

    seen_ids = [row["ResourceId"] for row in _read_csv(azure)]

    for suffix in PLANTED_AZURE_NAME_SUFFIXES:
        assert any(rid.endswith(suffix) for rid in seen_ids), (
            f"Missing planted Azure orphan with name suffix {suffix!r}; "
            f"saw {seen_ids!r}"
        )


def test_aws_orphan_total_matches_expected(generated: tuple[Path, Path]) -> None:
    aws, _ = generated

    total = sum(
        float(row["lineItem/UnblendedCost"])
        for row in _read_csv(aws)
        if row["lineItem/ResourceId"] in PLANTED_AWS_IDS
    )

    assert total == pytest.approx(EXPECTED_AWS_SUBTOTAL, abs=0.01)


def test_azure_orphan_total_matches_expected(generated: tuple[Path, Path]) -> None:
    _, azure = generated

    total = sum(
        float(row["CostInBillingCurrency"])
        for row in _read_csv(azure)
        if any(row["ResourceId"].endswith(suf) for suf in PLANTED_AZURE_NAME_SUFFIXES)
    )

    assert total == pytest.approx(EXPECTED_AZURE_SUBTOTAL, abs=0.01)


def test_grand_total_monthly_savings_matches_expected(generated: tuple[Path, Path]) -> None:
    aws, azure = generated

    aws_total = sum(
        float(row["lineItem/UnblendedCost"])
        for row in _read_csv(aws)
        if row["lineItem/ResourceId"] in PLANTED_AWS_IDS
    )
    azure_total = sum(
        float(row["CostInBillingCurrency"])
        for row in _read_csv(azure)
        if any(row["ResourceId"].endswith(suf) for suf in PLANTED_AZURE_NAME_SUFFIXES)
    )

    assert (aws_total + azure_total) == pytest.approx(
        EXPECTED_TOTAL_MONTHLY_SAVINGS, abs=0.01
    )


def test_aws_orphan_rows_carry_the_states_their_rules_key_on(
    generated: tuple[Path, Path],
) -> None:
    aws, _ = generated
    by_id = {row["lineItem/ResourceId"]: row for row in _read_csv(aws)}

    assert by_id["vol-0unattachedebs00001"]["resource/status"] == "available"
    assert by_id["i-0longstoppedec2001"]["resource/status"] == "stopped"
    assert by_id["eipalloc-0unassociated001"]["resource/status"] == "unassociated"
    assert by_id["snap-0orphanedsnap00001"]["resource/attached"] == "false"


def test_clean_aws_rows_use_states_that_no_rule_triggers_on(
    generated: tuple[Path, Path],
) -> None:
    aws, _ = generated
    by_id = {row["lineItem/ResourceId"]: row for row in _read_csv(aws)}

    assert by_id["vol-0healthyinuse00001"]["resource/status"] == "in-use"
    assert by_id["i-0runninginst00001"]["resource/status"] == "running"
    assert by_id["eipalloc-0associated001"]["resource/status"] == "associated"
    assert by_id["snap-0recentsnap00001"]["resource/attached"] == "true"


def test_azure_orphan_rows_carry_the_states_their_rules_key_on(
    generated: tuple[Path, Path],
) -> None:
    _, azure = generated
    by_suffix = {
        row["ResourceId"].split("/")[-1]: row for row in _read_csv(azure)
    }

    assert by_suffix["disk-unattached-demo-001"]["ResourceStatus"] == "unattached"
    assert by_suffix["vm-deallocated-demo-001"]["ResourceStatus"] == "deallocated"


def test_clean_azure_rows_use_states_that_no_rule_triggers_on(
    generated: tuple[Path, Path],
) -> None:
    _, azure = generated
    by_suffix = {
        row["ResourceId"].split("/")[-1]: row for row in _read_csv(azure)
    }

    assert by_suffix["disk-attached-demo-001"]["ResourceStatus"] == "attached"
    assert by_suffix["vm-running-demo-001"]["ResourceStatus"] == "running"
