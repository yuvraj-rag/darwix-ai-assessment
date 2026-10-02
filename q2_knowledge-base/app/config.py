"""Central configuration: paths and tunable settings."""

from pathlib import Path

# Project root = parent of the `app` package, so paths work from any cwd.
ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHROMA_DIR = ROOT / "data" / "chroma"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "business_loan_kb"

# all-MiniLM-L6-v2 silently truncates input at 256 word pieces (~150-180
# English words, fewer for number-heavy policy text). Chunks must stay below
# that or the end of every chunk is never embedded.
CHUNK_WORDS = 120
CHUNK_OVERLAP_WORDS = 20

# Word-trigram Jaccard similarity at/above which two documents are reported
# as near-duplicates (reported only, never deleted automatically).
NEAR_DUPLICATE_THRESHOLD = 0.7

# Corpus-level metadata stamped on every record.
PRODUCT = "business_loan"
SYNTHETIC = True
