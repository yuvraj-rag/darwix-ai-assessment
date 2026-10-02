import hashlib
import math
import re
import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def fake_embed(texts, dim=512):
    """Deterministic bag-of-words embedder so tests need no model download."""
    vectors = []

    for text in texts:
        vector = [0.0] * dim

        for word in re.findall(r"[a-z0-9]+", text.lower()):
            index = int(hashlib.md5(word.encode()).hexdigest(), 16) % dim
            vector[index] += 1.0

        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        vectors.append([v / norm for v in vector])

    return vectors


ELIGIBILITY_MD = """# Eligibility Criteria

**Version:** 1.2
**Effective date:** 2025-01-01

Applicants must show a minimum annual turnover of Rs 40 lakh.
The business vintage must be at least 3 years.
A credit score of 700 or above is required.
Applicants must also provide supporting evidence of income for review.
The lender may request additional records before approving the loan.
Sole proprietorships, partnerships and private limited companies may apply.
"""

DOCUMENTS_HTML = """<html><head><title>Docs | Darwix</title></head><body>
<nav>Home | Products | About | Careers | Login</nav>
<h1>Documents Required</h1>
<p>Version: 2.0 &nbsp; Effective date: 1 March 2025</p>
<p>Please submit your <b>GST returns</b> and <a href="#">bank statements</a> for the last 12 months.</p>
<table>
<tr><th>Document</th><th>Mandatory</th></tr>
<tr><td>PAN card</td><td>Yes</td></tr>
<tr><td>Address proof</td><td>Yes</td></tr>
</table>
<footer>Copyright 2025 Darwix Business Finance. All rights reserved.</footer>
</body></html>"""

PARTNER_HTML = """<html><body><h1>Partner Website</h1>
<p>Contact our partner desk at desk@partner-example.com or +91 98765 43210.
Reference customer CUST-2024-0042 with PAN ABCDE1234F for a sample case.</p>
<p>Working-capital financing is available to eligible MSMEs.</p></body></html>"""

LIMITS_CSV = """Loan Type,Minimum Amount,Maximum Amount,Tenor
Working capital loan,500000,5000000,12 months
Term loan,1000000,20000000,60 months
"""

REPAYMENT_LINES = [
    "Repayment Policy",
    "Version: 1.0",
    "Effective date: 2025-02-15",
    "The repayment period for a working capital loan is up to 36 months.",
    "Prepayment is allowed after 6 months with a 2 percent charge.",
]


@pytest.fixture
def raw_dir(tmp_path):
    """A small messy corpus covering every supported format and edge case."""
    raw = tmp_path / "raw"
    (raw / "nested").mkdir(parents=True)

    (raw / "eligibility_criteria.md").write_text(ELIGIBILITY_MD, encoding="utf-8")
    # Exact duplicate of the file above.
    (raw / "eligibility_criteria_copy.md").write_text(ELIGIBILITY_MD, encoding="utf-8")
    # Near duplicate: one number changed.
    (raw / "eligibility_v2.md").write_text(
        ELIGIBILITY_MD.replace("700", "720").replace("1.2", "1.3"), encoding="utf-8"
    )
    (raw / "documents_required.html").write_text(DOCUMENTS_HTML, encoding="utf-8")
    (raw / "nested" / "partner_website.html").write_text(PARTNER_HTML, encoding="utf-8")
    (raw / "loan_limits_table.csv").write_text(LIMITS_CSV, encoding="utf-8")

    pdf = pymupdf.open()
    page = pdf.new_page()
    y = 72
    for line in REPAYMENT_LINES:
        page.insert_text((72, y), line)
        y += 18
    pdf.save(raw / "repayment_policy.pdf")
    pdf.close()

    # Edge cases: scanned/blank PDF, corrupt PDF, unsupported, hidden file.
    blank = pymupdf.open()
    blank.new_page()
    blank.save(raw / "scanned.pdf")
    blank.close()
    (raw / "corrupt.pdf").write_bytes(b"not a pdf at all")
    (raw / "notes.docx").write_bytes(b"PK\x03\x04")
    (raw / ".DS_Store").write_bytes(b"junk")

    return raw
