"""
Knowledge-base pipeline.

    python -m app.pipeline ingest              # raw files -> records + chunks (JSON)
    python -m app.pipeline index               # chunks -> ChromaDB
    python -m app.pipeline build               # ingest + index
    python -m app.pipeline search "question"   # query the index
"""

import argparse
import json
import sys
from pathlib import Path

from app import config
from app.chunker import chunk_record
from app.cleaner import (
    clean_document,
    find_near_duplicates,
    remove_exact_duplicates,
)
from app.extractors import extract_directory
from app.records import build_record


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def ingest(
    raw_dir: str | Path = config.RAW_DIR,
    out_dir: str | Path = config.PROCESSED_DIR,
) -> dict:
    """Extract, clean and chunk everything in raw_dir; return a report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extracted = extract_directory(raw_dir)
    succeeded = [d for d in extracted if d["status"] == "success"]

    cleaned = [clean_document(d) for d in succeeded]

    # Documents can become empty after boilerplate removal.
    non_empty = [d for d in cleaned if d["text"]]
    empty = [d["source"] for d in cleaned if not d["text"]]

    unique, exact_duplicates = remove_exact_duplicates(non_empty)
    near_duplicates = find_near_duplicates(unique)

    records = [build_record(d).to_dict() for d in unique]
    chunks = [chunk for record in records for chunk in chunk_record(record)]

    _write_json(out_dir / "knowledge_records.json", records)
    _write_json(out_dir / "chunks.json", chunks)

    report = {
        "files_found": len(extracted),
        "extracted": len(succeeded),
        "skipped": [
            {"source": d["source"], "reason": d["message"]}
            for d in extracted if d["status"] == "skipped"
        ],
        "errors": [
            {"source": d["source"], "error": d["message"]}
            for d in extracted if d["status"] == "error"
        ],
        "empty_after_cleaning": empty,
        "exact_duplicates": exact_duplicates,
        "near_duplicate_candidates": near_duplicates,
        "pii_documents": [
            {"source": d["source"], "types": d["pii_types"]}
            for d in unique if d["pii"]
        ],
        "records": len(records),
        "chunks": len(chunks),
    }

    _write_json(out_dir / "ingest_report.json", report)

    return report


def _print_report(report: dict) -> None:
    print(f"Files found:          {report['files_found']}")
    print(f"Extracted:            {report['extracted']}")
    print(f"Skipped:              {len(report['skipped'])}")
    print(f"Errors:               {len(report['errors'])}")
    print(f"Exact duplicates:     {len(report['exact_duplicates'])}")
    print(f"Near-duplicate pairs: {len(report['near_duplicate_candidates'])}")
    print(f"Documents with PII:   {len(report['pii_documents'])}")
    print(f"Records / chunks:     {report['records']} / {report['chunks']}")

    for item in report["skipped"]:
        print(f"  skipped {item['source']}: {item['reason']}")

    for item in report["errors"]:
        print(f"  ERROR   {item['source']}: {item['error']}")

    for pair in report["near_duplicate_candidates"]:
        print(
            f"  similar ({pair['similarity']}): "
            f"{pair['document_a']} <-> {pair['document_b']}"
        )


def _print_hits(query: str, hits: list[dict]) -> None:
    print(f"\nQUERY: {query}")

    for rank, hit in enumerate(hits, start=1):
        meta = hit["metadata"]
        print(f"\n--- {rank}. {meta['source']} (score {hit['score']}) ---")
        print(
            f"Category: {meta['category']} | "
            f"Version: {meta['version']} | Chunk: {hit['chunk_id']}"
        )
        print(hit["content"][:500])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("ingest", help="extract, clean and chunk raw files")
    commands.add_parser("index", help="embed chunks into ChromaDB")
    commands.add_parser("build", help="ingest, then index")

    search_cmd = commands.add_parser("search", help="query the index")
    search_cmd.add_argument("queries", nargs="+")
    search_cmd.add_argument("-k", "--top-k", type=int, default=3)
    search_cmd.add_argument("--category", help="restrict to one category")

    args = parser.parse_args(argv)

    if args.command in {"ingest", "build"}:
        report = ingest()
        _print_report(report)

        if report["records"] == 0:
            print("\nNo documents were produced; check data/raw.", file=sys.stderr)
            return 1

    # Imported here so `ingest` works without chromadb / torch loaded.
    from app import vector_store

    if args.command in {"index", "build"}:
        count = vector_store.build_index()
        print(f"\nIndexed {count} chunks into {config.CHROMA_DIR}")

    if args.command == "search":
        collection = vector_store.get_collection()

        for query in args.queries:
            hits = vector_store.search(
                query,
                top_k=args.top_k,
                category=args.category,
                collection=collection,
            )
            _print_hits(query, hits)

    return 0


if __name__ == "__main__":
    sys.exit(main())
