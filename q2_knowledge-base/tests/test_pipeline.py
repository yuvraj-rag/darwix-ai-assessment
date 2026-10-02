import json

from app import pipeline, vector_store
from conftest import fake_embed


def test_ingest_end_to_end(raw_dir, tmp_path):
    out = tmp_path / "processed"
    report = pipeline.ingest(raw_dir, out)

    assert report["files_found"] == 10  # .DS_Store ignored
    assert [e["source"] for e in report["errors"]] == ["corrupt.pdf"]
    assert {s["source"] for s in report["skipped"]} == {"scanned.pdf", "notes.docx"}
    assert report["exact_duplicates"][0]["source"] == "eligibility_criteria_copy.md"
    assert len(report["near_duplicate_candidates"]) == 1
    assert report["pii_documents"] == [
        {"source": "nested/partner_website.html",
         "types": ["email", "pan", "customer_id", "phone"]}
    ]

    records = json.loads((out / "knowledge_records.json").read_text(encoding="utf-8"))
    by_source = {r["source"]: r for r in records}

    elig = by_source["eligibility_criteria.md"]
    assert (elig["version"], elig["effective_date"]) == ("1.2", "2025-01-01")
    assert "business operating history" in elig["content"]  # terminology normalised
    assert elig["category"] == "qualification" and elig["title"] == "Eligibility Criteria"

    docs = by_source["documents_required.html"]
    assert docs["effective_date"] == "2025-03-01" and docs["category"] == "documentation"
    assert "Copyright" not in docs["content"]

    partner = by_source["nested/partner_website.html"]
    assert partner["pii"] and "desk@partner" not in partner["content"]
    assert "ABCDE1234F" not in partner["content"]

    assert by_source["repayment_policy.pdf"]["effective_date"] == "2025-02-15"
    assert "tenor" in by_source["repayment_policy.pdf"]["content"]

    chunks = json.loads((out / "chunks.json").read_text(encoding="utf-8"))
    assert {c["record_id"] for c in chunks} == {r["record_id"] for r in records}
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)


def test_index_and_search(raw_dir, tmp_path):
    out, db = tmp_path / "processed", tmp_path / "chroma"
    pipeline.ingest(raw_dir, out)

    count = vector_store.build_index(out / "chunks.json", db, embed_fn=fake_embed)
    collection = vector_store.get_collection(db)
    assert collection.count() == count

    def top(query, **kw):
        hits = vector_store.search(query, collection=collection, embed_fn=fake_embed, **kw)
        return hits[0]["metadata"]["source"]

    assert top("minimum annual turnover") == "eligibility_criteria.md"
    assert top("what is the prepayment charge") == "repayment_policy.pdf"
    assert top("which documents do I need to submit") == "documents_required.html"
    assert top("term loan maximum amount", category="qualification") == "loan_limits_table.csv"


def test_rebuild_drops_stale_chunks(raw_dir, tmp_path):
    out, db = tmp_path / "processed", tmp_path / "chroma"
    pipeline.ingest(raw_dir, out)
    vector_store.build_index(out / "chunks.json", db, embed_fn=fake_embed)

    (raw_dir / "repayment_policy.pdf").unlink()
    pipeline.ingest(raw_dir, out)
    count = vector_store.build_index(out / "chunks.json", db, embed_fn=fake_embed)

    collection = vector_store.get_collection(db)
    assert collection.count() == count
    sources = {m["source"] for m in collection.get()["metadatas"]}
    assert "repayment_policy.pdf" not in sources


def test_search_preserves_legacy_contract_and_metadata(raw_dir, tmp_path):
    out, db = tmp_path / "processed", tmp_path / "chroma"
    pipeline.ingest(raw_dir, out)
    vector_store.build_index(out / "chunks.json", db, embed_fn=fake_embed)

    hits = vector_store.search(
        "what is the prepayment charge",
        top_k=3,
        collection=vector_store.get_collection(db),
        embed_fn=fake_embed,
    )

    assert hits
    assert all(set(hit) >= {"chunk_id", "score", "content", "metadata"} for hit in hits)
    assert all("source_authority" in hit["metadata"] for hit in hits)
    assert all("provenance" in hit["metadata"] for hit in hits)
