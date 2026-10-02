"""Clean extracted text: normalise, strip boilerplate, redact PII, deduplicate."""

import hashlib
import re
import unicodedata
from itertools import combinations

from app import config

# Terms that should have one canonical form (keys must be lowercase).
TERMINOLOGY = {
    "working-capital financing": "working capital loan",
    "working capital financing": "working capital loan",
    "working-capital loan": "working capital loan",
    "repayment period": "tenor",
    "repayment duration": "tenor",
    "business vintage": "business operating history",
}

_TERM_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(t) for t in sorted(TERMINOLOGY, key=len, reverse=True))
    + r")(s?)\b",
    flags=re.IGNORECASE,
)

_BOILERPLATE_PATTERNS = [
    re.compile(p, flags=re.IGNORECASE | re.MULTILINE)
    for p in (
        r"Home\s*\|\s*Personal Banking\s*\|\s*Cards\s*\|\s*Careers\s*\|\s*Contact\s*\|\s*Login",
        r"Home\s*\|\s*Products\s*\|\s*About\s*\|\s*Careers\s*\|\s*Login",
        r"Copyright\s+\d{4}\s+Darwix Business Finance\..*",
        r"Darwix Business Finance\s*\|\s*©\s*\d{4}\s*\|\s*All rights reserved",
        r"^\s*Page\s+\d+(\s+of\s+\d+)?\s*$",
    )
]

# Order matters: longer / more specific identifiers first, so that e.g. a
# GSTIN is not half-eaten by the PAN pattern.
_PII_PATTERNS = {
    "email": (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    "gstin": (
        re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"),
        "[REDACTED_GSTIN]",
    ),
    "pan": (
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        "[REDACTED_PAN]",
    ),
    "aadhaar": (
        re.compile(r"(?<!\d)\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)"),
        "[REDACTED_AADHAAR]",
    ),
    "customer_id": (
        re.compile(r"\bCUST-\d{4}-\d{4}\b", flags=re.IGNORECASE),
        "[REDACTED_CUSTOMER_ID]",
    ),
    "phone": (
        re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),
        "[REDACTED_PHONE]",
    ),
    "account_number": (
        re.compile(r"(?<!\d)\d{10,18}(?!\d)"),
        "[REDACTED_ACCOUNT]",
    ),
}


def normalize_unicode(text: str) -> str:
    """Fix PDF ligatures, non-breaking spaces and invisible characters."""
    text = unicodedata.normalize("NFKC", text)

    return re.sub(r"[\u200b\u200c\u200d\ufeff\u00ad]", "", text)


def normalize_whitespace(text: str) -> str:
    """Normalise line endings, trim lines, collapse blank-line runs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def remove_boilerplate(text: str) -> str:
    """Remove website navigation, footers and page-number lines."""
    for pattern in _BOILERPLATE_PATTERNS:
        text = pattern.sub("", text)

    return text


def normalize_terminology(text: str) -> str:
    """Convert known term variants into their canonical form."""

    def replace(match: re.Match) -> str:
        found = match.group(1)
        canonical = TERMINOLOGY[found.lower()]

        if found[0].isupper():
            canonical = canonical[0].upper() + canonical[1:]

        return canonical + match.group(2)

    return _TERM_PATTERN.sub(replace, text)


def redact_pii(text: str) -> tuple[str, list[str]]:
    """
    Redact obvious PII patterns; return (clean_text, pii_types_found).

    This is a pattern-based prototype detector. It will not catch names or
    addresses and is not a substitute for compliance tooling.
    """
    found = []

    for pii_type, (pattern, replacement) in _PII_PATTERNS.items():
        text, count = pattern.subn(replacement, text)

        if count:
            found.append(pii_type)

    return text, found


def content_hash(text: str) -> str:
    """Stable hash for exact duplicate detection."""
    return hashlib.sha256(text.lower().strip().encode("utf-8")).hexdigest()


def clean_document(document: dict) -> dict:
    """Run the full cleaning pipeline on one extracted document."""
    text = normalize_unicode(document.get("text", ""))
    text = remove_boilerplate(text)
    text = normalize_terminology(text)
    text = normalize_whitespace(text)
    text, pii_types = redact_pii(text)

    return {
        "source": document["source"],
        "file_type": document.get("file_type"),
        "title": document.get("title"),
        "text": text,
        "character_count": len(text),
        "content_hash": content_hash(text),
        "pii": bool(pii_types),
        "pii_types": pii_types,
    }


def remove_exact_duplicates(documents: list[dict]) -> tuple[list[dict], list[dict]]:
    """Keep the first copy of identical documents; report the rest."""
    seen = {}
    unique = []
    duplicates = []

    for document in documents:
        first = seen.get(document["content_hash"])

        if first is None:
            seen[document["content_hash"]] = document["source"]
            unique.append(document)
        else:
            duplicates.append({
                "source": document["source"],
                "duplicate_of": first,
                "type": "exact",
            })

    return unique, duplicates


def _shingles(text: str, size: int = 3) -> set[str]:
    words = text.lower().split()

    if len(words) <= size:
        return {" ".join(words)}

    return {" ".join(words[i:i + size]) for i in range(len(words) - size + 1)}


def find_near_duplicates(
    documents: list[dict],
    threshold: float = config.NEAR_DUPLICATE_THRESHOLD,
) -> list[dict]:
    """
    Report pairs of highly similar documents (e.g. two versions of one policy).

    Uses Jaccard similarity of 3-word shingles, which is far faster than
    character-level diffing. Pairs are compared in O(n^2); fine for thousands
    of documents, not millions. Nothing is deleted automatically.
    """
    shingles = [_shingles(d["text"]) for d in documents]
    candidates = []

    for i, j in combinations(range(len(documents)), 2):
        a, b = shingles[i], shingles[j]

        # Jaccard can never exceed the size ratio, so skip obvious misses.
        if min(len(a), len(b)) / max(len(a), len(b)) < threshold:
            continue

        score = len(a & b) / len(a | b)

        if score >= threshold:
            candidates.append({
                "document_a": documents[i]["source"],
                "document_b": documents[j]["source"],
                "similarity": round(score, 3),
                "type": "near_duplicate",
            })

    return candidates
