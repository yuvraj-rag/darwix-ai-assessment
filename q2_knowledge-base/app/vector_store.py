"""Build and query the ChromaDB vector index."""

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Callable

import chromadb

from app import config

EmbedFn = Callable[[list[str]], list[list[float]]]

BATCH_SIZE = 500
DENSE_CANDIDATES = 30
LEXICAL_CANDIDATES = 40


@lru_cache(maxsize=1)
def _load_model():
    # Imported lazily: loading torch is slow and not needed for ingestion.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config.EMBEDDING_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the configured model (normalised vectors)."""
    return _load_model().encode(
        texts, normalize_embeddings=True, batch_size=32
    ).tolist()


def _embedding_text(chunk: dict) -> str:
    # The title gives each chunk context it may lack on its own.
    return f"{chunk['title']}\n{chunk['content']}"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _is_archival(chunk: dict) -> bool:
    source = str(chunk.get("source", "")).lower()
    text = str(chunk.get("content", "")).lower()
    return any(token in source for token in ("old", "archive", "obsolete")) or (
        "archived copy" in text or "do not use this version" in text
    )


def _prune_obsolete_chunks(chunks: list[dict]) -> list[dict]:
    """Drop stale archival copies before indexing while keeping the newest record."""
    return [chunk for chunk in chunks if not _is_archival(chunk)]


def _client(db_path: str | Path | None):
    return chromadb.PersistentClient(path=str(db_path or config.CHROMA_DIR))


def build_index(
    chunks_file: str | Path | None = None,
    db_path: str | Path | None = None,
    embed_fn: EmbedFn = embed,
) -> int:
    """Rebuild the collection from chunks.json and return the chunk count."""
    chunks_file = Path(chunks_file or config.PROCESSED_DIR / "chunks.json")
    chunks = json.loads(chunks_file.read_text(encoding="utf-8"))

    if not chunks:
        raise ValueError(f"No chunks found in {chunks_file}; nothing to index.")

    chunks = _prune_obsolete_chunks(chunks)

    if not chunks:
        raise ValueError(f"No current chunks left after pruning stale records in {chunks_file}.")

    client = _client(db_path)

    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        config.COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        collection.add(
            ids=[c["chunk_id"] for c in batch],
            documents=[c["content"] for c in batch],
            embeddings=embed_fn([_embedding_text(c) for c in batch]),
            metadatas=[
                {k: v for k, v in c.items() if k not in {"chunk_id", "content"}}
                for c in batch
            ],
        )

    return len(chunks)


def get_collection(db_path: str | Path | None = None):
    client = _client(db_path)

    try:
        return client.get_collection(config.COLLECTION_NAME)
    except Exception:
        return client.create_collection(
            config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )


def _metadata_boost(metadata: dict) -> float:
    authority = str(metadata.get("source_authority", "unknown")).lower()
    provenance = str(metadata.get("provenance", "current")).lower()

    boost = {
        "official": 0.40,
        "internal": 0.25,
        "public": 0.12,
        "secondary": 0.08,
        "archival": -0.40,
        "unknown": 0.0,
    }.get(authority, 0.0)

    if provenance == "current":
        boost += 0.12
    if metadata.get("effective_date") not in (None, "unknown"):
        boost += 0.08
    if metadata.get("version") not in (None, "unknown"):
        boost += 0.06
    return boost


def _query_overlap(query: str, text: str) -> float:
    q_terms = set(_tokenize(query))
    d_terms = set(_tokenize(text))
    if not q_terms:
        return 0.0
    return len(q_terms & d_terms) / len(q_terms)


def _phrase_bonus(query: str, text: str) -> float:
    q = " ".join(_tokenize(query))
    d = " ".join(_tokenize(text))
    if len(q.split()) < 2:
        return 0.0
    return 1.0 if q in d else 0.0


def _bm25_score(query: str, text: str) -> float:
    """A transparent BM25-like signal for lexical matching."""
    q_terms = _tokenize(query)
    d_terms = _tokenize(text)
    if not q_terms or not d_terms:
        return 0.0

    tf = Counter(d_terms)
    doc_len = len(d_terms)
    avgdl = max(doc_len, 1)
    k1 = 1.5
    b = 0.75
    score = 0.0

    for term in set(q_terms):
        if term not in tf:
            continue
        df = 1.0
        idf = math.log((1.0 + 1.0) / (1.0 + df)) + 1.0
        normalized_tf = tf[term] * (k1 + 1.0) / (tf[term] + k1 * (1.0 - b + b * doc_len / avgdl))
        score += idf * normalized_tf

    return score


def _source_variant_penalty(source: str) -> float:
    lowered = source.lower()
    if any(token in lowered for token in ("old", "archive", "obsolete", "copy", "draft", "legacy")):
        return 0.30
    if "v2" in lowered or "v3" in lowered:
        return 0.20
    return 0.0


def _lexical_candidates(collection, query: str, category: str | None, limit: int) -> list[dict]:
    where = {"category": category} if category else None
    payload = collection.get(where=where, include=["documents", "metadatas"])

    scored = []
    for chunk_id, document, metadata in zip(payload["ids"], payload["documents"], payload["metadatas"]):
        if not document:
            continue
        score = _bm25_score(query, document)
        if score <= 0:
            continue
        scored.append({
            "chunk_id": chunk_id,
            "content": document,
            "metadata": metadata,
            "lexical": score,
        })

    scored.sort(key=lambda item: item["lexical"], reverse=True)
    return scored[:limit]


def _rank_hits(hits: list[dict], query: str) -> list[dict]:
    ranked = []
    for hit in hits:
        metadata = hit.get("metadata", {})
        dense = float(hit.get("dense", 0.0))
        lexical = float(hit.get("lexical", 0.0))
        overlap = _query_overlap(query, hit["content"])
        phrase = _phrase_bonus(query, hit["content"])
        authority = _metadata_boost(metadata)
        provenance = 1.0 if str(metadata.get("provenance", "current")).lower() == "current" else 0.0
        penalty = _source_variant_penalty(str(metadata.get("source", "")))

        lexical_norm = min(1.0, math.tanh(lexical / 4.0))
        final = (
            0.45 * dense
            + 0.25 * lexical_norm
            + 0.15 * overlap
            + 0.10 * phrase
            + 0.10 * authority
            + 0.05 * provenance
            - penalty
        )

        ranked.append({
            **hit,
            "score": round(max(final, 0.0), 4),
            "debug": {
                "final_score": round(max(final, 0.0), 4),
                "dense": round(dense, 4),
                "lexical": round(lexical_norm, 4),
                "overlap": round(overlap, 4),
                "authority": round(max(authority, 0.0), 4),
                "recency": round(provenance, 4),
            },
        })

    ranked.sort(key=lambda hit: (hit["score"], hit["debug"]["dense"], hit["debug"]["lexical"]), reverse=True)
    return ranked


def _select_diverse_topk(hits: list[dict], top_k: int) -> list[dict]:
    selected = []
    seen_sources = {}
    seen_records = set()

    for hit in hits:
        metadata = hit.get("metadata", {})
        record_id = metadata.get("record_id")
        source = metadata.get("source")

        if record_id in seen_records:
            continue
        if source and seen_sources.get(source, 0) >= 2:
            continue

        seen_records.add(record_id)
        if source:
            seen_sources[source] = seen_sources.get(source, 0) + 1
        selected.append(hit)

        if len(selected) >= top_k:
            break

    return selected


def search(
    query: str,
    top_k: int = 3,
    category: str | None = None,
    collection=None,
    embed_fn: EmbedFn = embed,
) -> list[dict]:
    """Return the top_k most similar chunks, best first."""
    collection = collection or get_collection()
    where = {"category": category} if category else None

    dense_result = collection.query(
        query_embeddings=embed_fn([query]),
        n_results=max(DENSE_CANDIDATES, top_k * 12),
        where=where,
    )

    merged = {}
    for chunk_id, content, metadata, distance in zip(
        dense_result["ids"][0],
        dense_result["documents"][0],
        dense_result["metadatas"][0],
        dense_result["distances"][0],
    ):
        merged[chunk_id] = {
            "chunk_id": chunk_id,
            "content": content,
            "metadata": metadata,
            "dense": round(1 - distance, 4),
            "lexical": 0.0,
        }

    for candidate in _lexical_candidates(collection, query, category, LEXICAL_CANDIDATES):
        entry = merged.setdefault(
            candidate["chunk_id"],
            {
                "chunk_id": candidate["chunk_id"],
                "content": candidate["content"],
                "metadata": candidate["metadata"],
                "dense": 0.0,
                "lexical": 0.0,
            },
        )
        entry["lexical"] = max(entry.get("lexical", 0.0), candidate["lexical"])

    ranked = _rank_hits([
        {
            "chunk_id": item["chunk_id"],
            "content": item["content"],
            "metadata": item["metadata"],
            "dense": float(item.get("dense", 0.0)),
            "lexical": float(item.get("lexical", 0.0)),
        }
        for item in merged.values()
    ], query)

    return [
        {
            "chunk_id": hit["chunk_id"],
            "score": hit["score"],
            "content": hit["content"],
            "metadata": hit["metadata"],
            "debug": hit["debug"],
        }
        for hit in _select_diverse_topk(ranked, top_k)
    ]


def retrieve(
    query: str,
    top_k: int = 5,
    category: str | None = None,
    collection=None,
    embed_fn: EmbedFn = embed,
) -> list[dict]:
    """Return human-readable retrieval hits with debug details and stable metadata."""
    hits = search(query, top_k=top_k, category=category, collection=collection, embed_fn=embed_fn)
    return [
        {
            "text": hit["content"],
            "source": hit["metadata"].get("source"),
            "category": hit["metadata"].get("category"),
            "version": hit["metadata"].get("version"),
            "effective_date": hit["metadata"].get("effective_date"),
            "source_type": hit["metadata"].get("source_type"),
            "record_id": hit["metadata"].get("record_id"),
            "score": hit["score"],
            "dense_score": hit.get("debug", {}).get("dense"),
            "lexical_score": hit.get("debug", {}).get("lexical"),
            "debug": hit.get("debug", {}),
        }
        for hit in hits
    ]
