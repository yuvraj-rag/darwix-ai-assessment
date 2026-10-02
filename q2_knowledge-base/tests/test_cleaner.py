from app.cleaner import (
    clean_document,
    find_near_duplicates,
    normalize_terminology,
    normalize_whitespace,
    redact_pii,
    remove_boilerplate,
    remove_exact_duplicates,
)


def test_terminology_preserves_case_and_plurals():
    assert normalize_terminology("Repayment period is fixed.") == "Tenor is fixed."
    assert normalize_terminology("many repayment periods") == "many tenors"
    assert normalize_terminology("Working-capital financing") == "Working capital loan"
    # No partial-word replacement.
    assert normalize_terminology("prerepayment periodic") == "prerepayment periodic"


def test_pii_redaction():
    text = (
        "mail a.b@x.com call +91 98765 43210 PAN ABCDE1234F "
        "acct 123456789012 GST 27ABCDE1234F1Z5 CUST-2024-0042 aadhaar 2345 6789 0123"
    )
    clean, found = redact_pii(text)

    for secret in ("a.b@x.com", "98765", "ABCDE1234F", "123456789012",
                   "27ABCDE1234F1Z5", "CUST-2024", "2345 6789"):
        assert secret not in clean
    assert set(found) == {"email", "phone", "pan", "account_number",
                          "gstin", "aadhaar", "customer_id"}


def test_pii_does_not_touch_ordinary_numbers_or_words():
    text = "Loan of 5000000 over 36 months, interest 14.5%, Hello1234x, 700 score"
    clean, found = redact_pii(text)

    assert clean == text and found == []


def test_boilerplate_and_whitespace():
    text = "Home | Products | About | Careers | Login\nBody\nPage 2 of 9\n\n\n\n  Next  \r\n"
    cleaned = normalize_whitespace(remove_boilerplate(text))

    assert cleaned == "Body\n\nNext"


def test_clean_document_normalises_unicode():
    doc = clean_document({"source": "a.pdf", "text": "e\ufb03cient\u00a0loan\u200b"})

    assert doc["text"] == "efficient loan"


def test_duplicates():
    a = clean_document({"source": "a.md", "text": "same text here"})
    b = clean_document({"source": "b.md", "text": "Same   Text here"})
    unique, dups = remove_exact_duplicates([a, b])

    assert [d["source"] for d in unique] == ["a.md"]
    assert dups == [{"source": "b.md", "duplicate_of": "a.md", "type": "exact"}]


def test_near_duplicates_flag_versions_but_not_unrelated_docs():
    base = " ".join(f"word{i}" for i in range(100))
    v2 = base.replace("word50", "changed")
    other = " ".join(f"other{i}" for i in range(100))
    docs = [clean_document({"source": s, "text": t})
            for s, t in [("v1", base), ("v2", v2), ("x", other)]]

    pairs = find_near_duplicates(docs)

    assert [(p["document_a"], p["document_b"]) for p in pairs] == [("v1", "v2")]
