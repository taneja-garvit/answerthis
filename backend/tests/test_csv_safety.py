from datetime import datetime

import pytest

from app.services.audit_export import export_filename, sanitize_csv_cell


@pytest.mark.parametrize(
    "value",
    ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\t=1", "\r=1", "  =1+1"],
)
def test_formula_like_cells_are_neutralized(value):
    assert sanitize_csv_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["Plain text", "OR 0.81 (95% CI 0.69–0.95)", "19% lower", ""])
def test_ordinary_cells_unchanged(value):
    assert sanitize_csv_cell(value) == value


def test_none_becomes_empty():
    assert sanitize_csv_cell(None) == ""


def test_export_filename_is_sanitized():
    name = export_filename('../../etc/passwd"; rm -rf / <script>', "csv", datetime(2026, 1, 2))
    assert name == "evidence-review-etc-passwd-rm-rf-script-20260102.csv"
    assert "/" not in name and '"' not in name


def test_export_filename_fallback_for_symbol_only_title():
    assert export_filename("—!!—", "json", datetime(2026, 1, 2)) == (
        "evidence-review-project-20260102.json"
    )


def test_export_filename_truncates_long_titles():
    name = export_filename("a" * 500, "csv", datetime(2026, 1, 2))
    assert len(name) <= len("evidence-review--20260102.csv") + 60
