import pytest

from app.chunker import chunk_record, chunk_text


def words(n, prefix="w"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_empty_and_short_text():
    assert chunk_text("") == []
    assert chunk_text("hello world") == ["hello world"]


def test_chunks_respect_size_and_cover_everything():
    paragraphs = [words(30, f"p{i}_") for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, chunk_size=100, overlap=20)

    assert all(len(c.split()) <= 100 for c in chunks)
    joined = "\n".join(chunks)
    assert all(p in joined for p in paragraphs)  # nothing lost, paragraphs intact


def test_overlap_repeats_trailing_context():
    paragraphs = [words(15, f"p{i}_") for i in range(10)]
    chunks = chunk_text("\n\n".join(paragraphs), chunk_size=50, overlap=20)

    assert paragraphs[2] in chunks[0] and paragraphs[2] in chunks[1]


def test_oversized_line_is_split_by_words():
    chunks = chunk_text(words(250), chunk_size=100, overlap=10)

    assert [len(c.split()) for c in chunks] == [100, 100, 50]


def test_table_rows_are_not_cut_mid_row():
    rows = [f"Type: T{i} | Min: {i}000 | Max: {i}0000" for i in range(60)]
    chunks = chunk_text("\n".join(rows), chunk_size=60, overlap=10)

    for chunk in chunks:
        for line in chunk.splitlines():
            assert line in rows


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_settings_raise(size, overlap):
    with pytest.raises(ValueError):
        chunk_text("a b c", chunk_size=size, overlap=overlap)


def test_chunk_record_inherits_metadata():
    record = {"record_id": "KB-1", "title": "T", "content": words(300),
              "category": "faq", "source": "s.md"}
    chunks = chunk_record(record)

    assert len(chunks) > 1
    assert chunks[0]["chunk_id"] == "KB-1-C1" and chunks[1]["chunk_index"] == 1
    assert all(c["category"] == "faq" and c["title"] == "T" for c in chunks)
