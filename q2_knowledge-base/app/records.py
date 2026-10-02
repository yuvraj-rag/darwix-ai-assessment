"""Turn cleaned documents into knowledge records with metadata."""

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from app import config


@dataclass
class KnowledgeRecord:
    record_id: str
    title: str
    content: str

    category: str
    product: str

    source: str
    source_type: str
    source_authority: str
    provenance: str

    version: str
    effective_date: str

    pii: bool  # True if PII was found (and redacted) in the original
    synthetic: bool

    def to_dict(self) -> dict:
        return asdict(self)


# Filename rules, checked in order. Patterns run against the lowercase name
# with separators turned into spaces, so "form" does not match "information".
_NAME_RULES = [
    (r"\b(application|forms?)\b", "application"),
    (r"\beligib", "qualification"),
    (r"\bdocument", "documentation"),
    (r"\b(repay|polic)", "policy"),
    (r"\b(faq|objection)", "faq"),
    (r"\b(partner|website)", "product"),
    (r"\btables?\b", "qualification"),
    (r"\bproduct", "product"),
]

# Fallback when the filename says nothing: most frequent keyword wins.
_TEXT_KEYWORDS = {
    "qualification": "eligib",
    "policy": "repayment",
    "faq": "objection",
}

_SOURCE_TYPES = {
    ".html": "website",
    ".htm": "website",
    ".pdf": "pdf",
    ".docx": "document",
    ".csv": "table",
    ".md": "document",
    ".txt": "document",
}

_ACRONYMS = {"faq", "kyc", "emi", "gst", "msme", "sme"}

_DATE = (
    r"(\d{4}-\d{2}-\d{2}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})"
)
_DATE_FORMATS = ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y")


def title_from_filename(source: str) -> str:
    words = re.split(r"[-_\s]+", Path(source).stem)

    return " ".join(
        w.upper() if w.lower() in _ACRONYMS else w.capitalize()
        for w in words
        if w
    )


def detect_category(source: str, text: str) -> str:
    name = re.sub(r"[-_.]+", " ", Path(source).stem.lower())

    for pattern, category in _NAME_RULES:
        if re.search(pattern, name):
            return category

    text_lower = text.lower()
    counts = {c: text_lower.count(k) for c, k in _TEXT_KEYWORDS.items()}
    best = max(counts, key=counts.get)

    return best if counts[best] else "general"


def detect_source_type(source: str) -> str:
    return _SOURCE_TYPES.get(Path(source).suffix.lower(), "unknown")


def _parse_date(raw: str) -> str:
    """Return an ISO date (YYYY-MM-DD), or "unknown" if unparseable."""
    raw = re.sub(r"\s+", " ", raw.strip())

    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, date_format).date().isoformat()
        except ValueError:
            continue

    return "unknown"


def extract_metadata(text: str) -> tuple[str, str]:
    """Find "Version: 1.2" and "Effective date: ..." in the document text."""
    version_match = re.search(
        r"\bVersion\s*[:|*]*\s*v?([0-9]+(?:\.[0-9]+)*)",
        text,
        flags=re.IGNORECASE,
    )
    date_match = re.search(
        r"Effective\s+date\s*[:|*\-]*\s*" + _DATE,
        text,
        flags=re.IGNORECASE,
    )

    version = version_match.group(1) if version_match else "unknown"
    effective_date = _parse_date(date_match.group(1)) if date_match else "unknown"

    return version, effective_date


def detect_source_authority(source: str, text: str, category: str | None = None) -> str:
    """Rank how authoritative the record is for retrieval and ranking."""
    source_lower = source.lower()
    text_lower = text.lower()

    if any(token in source_lower for token in ("policy", "criteria", "terms", "agreement")):
        return "official"
    if category in {"policy", "qualification"}:
        return "official"
    if "partner" in source_lower or "customer" in source_lower:
        return "secondary"
    if any(token in text_lower for token in ("archived", "do not use this version", "old copy")):
        return "archival"
    if category in {"faq", "general"} or source_lower.endswith(".html"):
        return "public"
    return "unknown"


def detect_provenance(source: str, text: str) -> str:
    """Flag whether a record appears current or stale/archival."""
    source_lower = source.lower()
    text_lower = text.lower()

    if any(token in source_lower for token in ("old", "archive", "obsolete")):
        return "archival"
    if "archived copy" in text_lower or "do not use this version" in text_lower:
        return "archival"
    return "current"


def build_record(document: dict) -> KnowledgeRecord:
    source = document["source"]
    text = document["text"]
    category = detect_category(source, text)
    version, effective_date = extract_metadata(text)

    return KnowledgeRecord(
        record_id=f"KB-{document['content_hash'][:12]}",
        title=document.get("title") or title_from_filename(source),
        content=text,
        category=category,
        product=config.PRODUCT,
        source=source,
        source_type=detect_source_type(source),
        source_authority=detect_source_authority(source, text, category),
        provenance=detect_provenance(source, text),
        version=version,
        effective_date=effective_date,
        pii=document["pii"],
        synthetic=config.SYNTHETIC,
    )