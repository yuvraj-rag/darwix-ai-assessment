# Q2 — Knowledge Base / RAG Pipeline

A small end-to-end Retrieval-Augmented Generation (RAG) knowledge base built for the Darwix AI engineering assignment.

The system takes a collection of heterogeneous documents, extracts and cleans their content, detects PII, removes duplicates, creates structured records and chunks, generates embeddings, indexes them in Chroma, and retrieves relevant evidence for a user query.

The corpus used in this project is **fully synthetic** and represents fictional business-loan/service documents. It is intended only for demonstrating the pipeline.

---

## What the pipeline does

```text
Raw documents
     ↓
Extraction
     ↓
Cleaning & normalization
     ↓
PII detection / redaction
     ↓
Deduplication
     ↓
Canonical records
     ↓
Chunking
     ↓
Embeddings
     ↓
Chroma vector database
     ↓
Hybrid retrieval
     ↓
Reranking
     ↓
Relevant evidence + source metadata
```

The retrieval layer is designed to be consumed by Q1, where retrieved evidence can be passed to an LLM to generate grounded answers.

---

## Project structure

```text
q2_knowledge-base/
│
├── app/
│   ├── api.py
│   ├── cleaner.py
│   ├── chunker.py
│   ├── config.py
│   ├── extractors.py
│   ├── pipeline.py
│   ├── records.py
│   ├── vector_store.py
│   └── __init__.py
│
├── data/
│   ├── chroma/
│   ├── processed/
│   └── raw/
│
├── tests/
│   ├── conftest.py
│   ├── test_chunker.py
│   ├── test_cleaner.py
│   ├── test_extractors.py
│   ├── test_pipeline.py
│   └── test_records.py
│
├── requirements.txt
├── README.md
├── verify_retrieval.py
└── .gitignore
```

---

## Requirements

* Python 3.10+
* A virtual environment
* Internet access on the first run to download the embedding/reranking models

The main libraries include:

* PyMuPDF — PDF extraction
* BeautifulSoup — HTML extraction
* pandas — CSV/table handling
* python-docx — DOCX extraction
* sentence-transformers — embeddings and reranking
* ChromaDB — vector storage
* rank-bm25 — lexical retrieval
* FastAPI / Uvicorn — optional API integration

---

## Setup

From the project directory:

### 1. Create a virtual environment

```bash
python -m venv .venv
```

### 2. Activate it

Windows:

```powershell
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Build the knowledge base

The pipeline can be run in stages.

### Extract documents

```bash
python scripts/test_extraction.py
```

This scans the raw corpus and reports successful and failed extractions.

A failed/broken document is intentionally retained in the synthetic dataset to demonstrate extraction error handling.

### Clean and deduplicate

```bash
python scripts/run_cleaning.py
```

This performs text normalization, terminology normalization, PII detection/redaction, hashing, and duplicate detection.

### Build canonical records

```bash
python scripts/build_records.py
```

### Build chunks

```bash
python scripts/build_chunks.py
```

### Build/update the vector index

Run the indexing step provided by the current pipeline implementation.

The vector database is stored locally under:

```text
data/chroma/
```

---

## Searching the knowledge base

The easiest way to test retrieval is:

```bash
python -m app.pipeline search "What is the minimum annual turnover?"
```

Other useful examples:

```bash
python -m app.pipeline search "What documents are required?"
```

```bash
python -m app.pipeline search "What is the maximum loan amount?"
```

```bash
python -m app.pipeline search "What repayment tenor is available?"
```

The output shows the retrieved evidence, relevance score, source document, category, version, and chunk information.

---

## Retrieval approach

The system does not rely only on vector similarity.

It uses a combination of:

1. **Dense retrieval** using `all-MiniLM-L6-v2` and Chroma.
2. **Lexical retrieval** using BM25 for exact terms, numbers, dates, names, and phrases.
3. **Candidate merging and deduplication**.
4. **Cross-encoder reranking** to evaluate query/document relevance more directly.
5. **Metadata-aware ranking** using information such as source authority, category, version, and effective date.

This helps avoid cases where a semantically similar but irrelevant document outranks the document that actually contains the required evidence.

---

## Provenance and versioning

Each knowledge record and chunk retains metadata such as:

```text
record_id
title
category
product
source
source_type
source_section
version
effective_date
PII status
synthetic flag
```

This allows retrieved answers to be traced back to their source.

Older policy versions are retained where appropriate, while the retrieval layer can prefer newer/current authoritative information.

---

## PII handling

The corpus contains synthetic PII for testing.

The cleaning stage detects patterns such as:

* Email addresses
* Phone numbers
* PAN-like identifiers
* Account-like numbers
* Customer IDs

Detected PII is redacted before the content is used in the searchable knowledge base.

The data is fictional and does not contain real customer information.

---

## Retrieval evaluation

The project includes retrieval tests covering different types of questions, including:

* Eligibility
* Required documents
* Loan amounts
* Repayment terms
* Business operating history
* Date/event queries
* Policy questions

Each test can be evaluated using the retrieved evidence, source, relevance, and whether the result contains the information needed to answer the query.

The purpose is not just to show that search returns documents, but to demonstrate whether it returns the **right evidence**.

---

## Q1 integration

Q1 can consume retrieval results through the retrieval interface rather than interacting directly with Chroma.

Conceptually:

```python
results = retrieve(
    query="What documents do I need?",
    top_k=5
)
```

A result contains information such as:

```python
{
    "chunk_id": "...",
    "content": "...",
    "score": 0.87,
    "source": "documentation.md",
    "category": "documentation",
    "version": "1.1",
    "effective_date": "2026-09-01"
}
```

This gives Q1 the evidence needed to produce grounded answers and cite the underlying source.

---

## Synthetic data notice

All documents in `data/raw/` are fictional and were created specifically for this assignment.

They should not be interpreted as real documents, policies, customers, transactions, or company records.

See:

```text
data/SOURCE_NOTICE.md
```

for the corpus notice and:

```text
data/corpus_manifest.json
```

for the dataset manifest.

---

## Known limitations

This is an assignment prototype rather than a production knowledge platform.

Some intentional limitations include:

* Synthetic documents rather than real company data.
* PDF extraction can occasionally produce imperfect characters.
* Retrieval quality depends on the embedding and reranking models.
* The taxonomy and authority model are intentionally lightweight.
* OCR for scanned documents is not implemented as a full production pipeline.
* No external/cloud vector database is required.

These trade-offs keep the system small enough to understand and demonstrate while still covering the main stages of a practical RAG pipeline.

---

## Running the demo

A typical workflow is:

```bash
# Activate environment
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run extraction/processing steps as required
python scripts/test_extraction.py
python scripts/run_cleaning.py
python scripts/build_records.py
python scripts/build_chunks.py

# Test retrieval
python -m app.pipeline search "What is the minimum annual turnover?"
```

The resulting evidence can then be passed directly to the Q1 voice-agent pipeline.
