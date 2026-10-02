import pytest

from app.records import (
    detect_category,
    detect_source_type,
    extract_metadata,
    title_from_filename,
)


@pytest.mark.parametrize("name,expected", [
    ("eligibility_criteria.md", "qualification"),
    ("loan_application_form.pdf", "application"),
    ("information_sheet.md", "general"),       # "form" inside a word must not match
    ("repayment_policy.pdf", "policy"),
    ("objection_handling.md", "faq"),
    ("faq.md", "faq"),
    ("partner_website.html", "product"),
    ("documents_required.html", "documentation"),
    ("loan_limits_table.csv", "qualification"),
])
def test_category_from_filename(name, expected):
    assert detect_category(name, "") == expected


def test_category_text_fallback_and_filename_priority():
    assert detect_category("notes.md", "eligibility eligible eligibility") == "qualification"
    assert detect_category("notes.md", "nothing relevant") == "general"
    # A FAQ that merely mentions eligibility stays a FAQ.
    assert detect_category("faq.md", "eligibility eligibility") == "faq"


def test_source_type():
    assert detect_source_type("a/b.HTM") == "website"
    assert detect_source_type("a.txt") == "document"
    assert detect_source_type("a.xyz") == "unknown"


@pytest.mark.parametrize("text,version,date", [
    ("**Version:** 1.2\n**Effective date:** 2025-01-01", "1.2", "2025-01-01"),
    ("Version: 2.0 Effective date: 1 March 2025", "2.0", "2025-03-01"),
    ("Version | v3\nEffective date | March 5, 2024", "3", "2024-03-05"),
    ("no metadata here", "unknown", "unknown"),
    ("Effective date: 2025-13-45", "unknown", "unknown"),
])
def test_extract_metadata(text, version, date):
    assert extract_metadata(text) == (version, date)


def test_titles():
    assert title_from_filename("data/faq-for_kyc.md") == "FAQ For KYC"
