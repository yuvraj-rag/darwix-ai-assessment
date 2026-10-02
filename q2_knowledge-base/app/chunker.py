"""Split text into overlapping, paragraph-aware chunks."""

from app import config


def _word_count(text: str) -> int:
    return len(text.split())


def _units(text: str, max_words: int) -> list[str]:
    """
    Break text into pieces that each fit in a chunk: paragraphs first, then
    lines (CSV rows, PDF lines), then raw words for pathological long lines.
    """
    units = []

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if _word_count(paragraph) <= max_words:
            units.append(paragraph)
            continue

        for line in paragraph.split("\n"):
            words = line.split()

            for start in range(0, len(words), max_words):
                units.append(" ".join(words[start:start + max_words]))

    return units


def chunk_text(
    text: str,
    chunk_size: int = config.CHUNK_WORDS,
    overlap: int = config.CHUNK_OVERLAP_WORDS,
) -> list[str]:
    """
    Pack paragraphs/lines into chunks of at most ``chunk_size`` words.

    Chunks break on paragraph or line boundaries, so sentences and table rows
    are never cut in half. Each chunk starts with up to ``overlap`` words of
    trailing context from the previous one.
    """
    if chunk_size <= 0 or not 0 <= overlap < chunk_size:
        raise ValueError("Need chunk_size > 0 and 0 <= overlap < chunk_size.")

    chunks = []
    current: list[str] = []
    count = 0

    for unit in _units(text, chunk_size):
        size = _word_count(unit)

        if current and count + size > chunk_size:
            chunks.append("\n".join(current))

            # Carry trailing units forward as overlap.
            carried, carried_words = [], 0

            for previous in reversed(current):
                words = _word_count(previous)

                if carried_words + words > overlap:
                    break

                carried.insert(0, previous)
                carried_words += words

            if carried_words + size > chunk_size:
                carried, carried_words = [], 0

            current, count = carried, carried_words

        current.append(unit)
        count += size

    if current:
        chunks.append("\n".join(current))

    return chunks


def chunk_record(record: dict) -> list[dict]:
    """Chunk one knowledge record; each chunk inherits the record's metadata."""
    metadata = {key: value for key, value in record.items() if key != "content"}

    return [
        {
            **metadata,
            "chunk_id": f"{record['record_id']}-C{index + 1}",
            "chunk_index": index,
            "content": content,
        }
        for index, content in enumerate(chunk_text(record["content"]))
    ]
