"""Turn raw files (HTML, PDF, DOCX, Markdown/text, CSV) into plain text.

Every extractor returns a dict with at least ``text``; it may also return
``title``, ``page_count``, ``row_count`` and ``column_count``. To support a new
file type, write an extractor and add it to ``EXTRACTORS``.
"""

import csv
import io
import re
import zipfile
from itertools import zip_longest
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup
from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

# Tags that are page chrome, not knowledge.
_NOISE_TAGS = ["head", "script", "style", "noscript", "nav", "header", "footer"]

# Tags that should start/end a new line in the extracted text.
_BLOCK_TAGS = [
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "tr", "br", "pre", "blockquote",
]


def read_text_file(path: Path) -> str:
    """Read a text file; fall back to cp1252 for Windows-exported files."""
    raw = path.read_bytes()

    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _table_lines(header: list[str] | None, rows: list[list[str]]) -> list[str]:
    """One line per row: ``Header: value | Header: value`` (or plain cells)."""
    lines = []

    for row in rows:
        if header:
            parts = [
                f"{name}: {value}" if name else value
                for name, value in zip_longest(header, row, fillvalue="")
                if value
            ]
        else:
            parts = [value for value in row if value]

        if parts:
            lines.append(" | ".join(parts))

    return lines


def _html_table_text(table) -> str:
    trs = table.find_all("tr")
    rows = [
        [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
        for tr in trs
    ]
    has_header = (
        len(rows) > 1
        and trs[0].find("th") is not None
        and trs[0].find("td") is None
    )
    header, body = (rows[0], rows[1:]) if has_header else (None, rows)

    return "\n".join(_table_lines(header, body))


def extract_html(path: Path) -> dict:
    soup = BeautifulSoup(read_text_file(path), "html.parser")

    # Take the title before page chrome (which may contain it) is removed.
    heading = soup.find("h1") or soup.find("title")
    title = heading.get_text(" ", strip=True) if heading else None

    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    # Keep table rows together instead of one cell per line.
    for table in soup.find_all("table"):
        if table.find_parent("table") is None:
            table.replace_with("\n" + _html_table_text(table) + "\n")

    # Break lines at block elements only, so inline tags (<b>, <a>) don't
    # split sentences apart.
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")

    return {"text": soup.get_text(), "title": title or None}


def extract_pdf(path: Path) -> dict:
    with pymupdf.open(path) as document:
        if document.needs_pass:
            raise ValueError("PDF is password-protected")

        pages = [page.get_text("text") for page in document]

        return {
            "text": "\n\n".join(page for page in pages if page.strip()),
            "page_count": len(document),
        }


# Text-bearing nodes of a paragraph, in order, skipping deleted text and the
# duplicate (VML) fallback copy of drawings. Tracked insertions, hyperlinks,
# field results and text boxes are all included.
_TEXT_NODES = (
    ".//*[self::w:t or self::w:tab or self::w:br or self::w:cr"
    " or self::w:noBreakHyphen]"
    "[not(ancestor::w:del or ancestor::w:moveFrom"
    " or ancestor::*[local-name()='Fallback'])]"
)


def _paragraph_text(p) -> str:
    """Read from the XML: python-docx's ``Paragraph.text`` misses tracked insertions."""
    parts = []

    for node in p.xpath(_TEXT_NODES):
        tag = node.tag.rsplit("}", 1)[1]

        if tag == "t":
            parts.append(node.text or "")
        elif tag == "tab":
            parts.append(" ")
        elif tag == "noBreakHyphen":
            parts.append("-")
        elif node.get(qn("w:type")) in (None, "textWrapping"):  # not a page break
            parts.append("\n")

    return re.sub(r"\s*\n\s*", "\n", re.sub(r"[^\S\n]+", " ", "".join(parts))).strip()


def _iter_blocks(container, parent):
    """Yield Paragraph and Table objects in order, looking inside content controls."""
    for child in container.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)
        elif child.tag == qn("w:sdt"):
            for content in child.iterchildren(qn("w:sdtContent")):
                yield from _iter_blocks(content, parent)


def _paragraph_kind(paragraph) -> tuple[str, int]:
    """Classify as ("toc" | "heading" | "list" | "text", heading level; 0 = Title)."""
    styles, style = [], paragraph.style

    while style is not None and len(styles) < 10:  # style -> its base styles
        styles.append(style)
        style = style.base_style

    # The style id is language-neutral, the name may be localised.
    names = [n.lower() for s in styles for n in (s.name or "", s.style_id or "")]

    if any(n.startswith("toc") for n in names):
        return "toc", 0

    for name in names:
        match = re.fullmatch(r"title|heading ?([1-9])", name)

        if match:
            return "heading", int(match.group(1) or 0)

    # Direct formatting first, then styles: outline level makes a heading,
    # a numbering id (other than 0, "none") makes a list item.
    elements = [paragraph._p] + [s.element for s in styles]

    for element in elements:
        level = element.xpath("./w:pPr/w:outlineLvl/@w:val")

        if level and int(level[0]) < 9:
            return "heading", int(level[0]) + 1

    for element in elements:
        numbering = element.xpath("./w:pPr/w:numPr/w:numId/@w:val")

        if numbering:
            return ("list" if numbering[0] != "0" else "text"), 0

    return ("list" if any(n.startswith(("list bullet", "list number")) for n in names)
            else "text"), 0


def _cell_text(cell) -> str:
    parts = [
        "; ".join(_docx_table(block)) if isinstance(block, Table)  # nested table
        else _paragraph_text(block._p)
        for block in _iter_blocks(cell._tc, cell)
    ]

    return " ".join(" ".join(parts).split())


def _is_header_row(tr, cells) -> bool:
    """A row Word marks as a header, or whose text is entirely bold."""
    if tr.xpath("./w:trPr/w:tblHeader"):
        return True

    def bold(style):
        return style is not None and bool(style.font.bold)

    runs = [
        (paragraph, run)
        for cell in cells for paragraph in cell.paragraphs for run in paragraph.runs
        if run.text.strip()
    ]

    return bool(runs) and all(
        run.bold if run.bold is not None else bold(run.style) or bold(paragraph.style)
        for paragraph, run in runs
    )


def _docx_table(table) -> list[str]:
    grid, width = table._cells, len(table.columns)  # merges already expanded
    rows = []

    for index, row in enumerate(table.rows):
        cells = grid[index * width:(index + 1) * width]
        texts = [_cell_text(cell) for cell in cells]

        if any(texts):
            # A horizontally merged cell repeats across its columns; keep one copy.
            own = [
                "" if i and cell._tc is cells[i - 1]._tc else text
                for i, (cell, text) in enumerate(zip(cells, texts))
            ]
            rows.append((row._tr, cells, texts, own))

    lines = []

    # A merged title row ("Fee schedule" across all columns).
    while rows and len(rows[0][2]) > 1 and len({t for t in rows[0][2] if t}) == 1:
        lines.append(next(t for t in rows.pop(0)[2] if t))

    header = None

    if len(rows) > 1 and len({t for t in rows[0][2] if t}) > 1 and _is_header_row(*rows[0][:2]):
        header = rows.pop(0)[2]

    return lines + _table_lines(header, [own for *_, own in rows])


def extract_docx(path: Path) -> dict:
    """
    Word documents, in document order. Title/Heading N become ``#`` headings
    (kept attached to the text below them), list items become ``- `` lines and
    tables become one line per row. Headers, footers, footnotes, comments and
    tables of contents are left out; list numbering is not preserved.
    """
    raw = path.read_bytes()

    if raw.startswith(b"\xd0\xcf\x11\xe0"):
        raise ValueError("not a valid .docx file (old .doc renamed to .docx)")

    try:
        with zipfile.ZipFile(path) as zf:
            if "word/document.xml" not in zf.namelist():
                raise _DocxSkipError("invalid .docx (missing document content)")
    except zipfile.BadZipFile as exc:
        raise _DocxSkipError(f"invalid .docx ({type(exc).__name__}: {exc})") from exc

    try:
        document = Document(str(path))
    except PackageNotFoundError as exc:
        raise ValueError(
            "not a valid .docx file (corrupt, password-protected, "
            "or an old .doc renamed to .docx)"
        ) from exc

    blocks, headings, previous = [], [], None

    for block in _iter_blocks(document.element.body, document):
        if isinstance(block, Table):
            text, kind = "\n".join(_docx_table(block)), "table"
        else:
            kind, level = _paragraph_kind(block)
            text = _paragraph_text(block._p)

            if kind == "toc" or not text:
                continue

            if kind == "heading":
                text = text.replace("\n", " ")
                headings.append((level, text))
                text = "#" * max(level, 1) + " " + text
            elif kind == "list":
                text = "- " + text

        if not text:
            continue

        # Keep a heading with what follows it, and list items together.
        if blocks and (previous == "heading" or previous == kind == "list"):
            blocks[-1] += "\n" + text
        else:
            blocks.append(text)

        previous = kind

    # A Title paragraph wins; otherwise the first heading.
    title = next((t for level, t in headings if level == 0),
                 headings[0][1] if headings else None)

    return {"text": "\n\n".join(blocks), "title": title}


def extract_text_file(path: Path) -> dict:
    """Markdown and plain text."""
    text = read_text_file(path)
    heading = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)

    return {"text": text, "title": heading.group(1).strip() if heading else None}


def extract_csv(path: Path) -> dict:
    """Turn each CSV row into one ``Column: value | Column: value`` line."""
    text = read_text_file(path)

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text, newline=""), dialect=dialect)

    lines = []
    row_count = 0

    for row in reader:
        row_count += 1
        parts = [
            f"{key.strip()}: {value.strip()}"
            for key, value in row.items()
            if key and isinstance(value, str) and value.strip()
        ]
        if parts:
            lines.append(" | ".join(parts))

    return {
        "text": "\n".join(lines),
        "row_count": row_count,
        "column_count": len(reader.fieldnames or []),
    }


EXTRACTORS = {
    ".html": extract_html,
    ".htm": extract_html,
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".md": extract_text_file,
    ".txt": extract_text_file,
    ".csv": extract_csv,
}


# Extra advice appended to the "unsupported file type" message.
_UNSUPPORTED_HINTS = {
    ".doc": "legacy Word format; re-save as .docx",
    ".rtf": "rich-text format is not supported; export as .txt or .docx",
    ".xls": "legacy Excel format; export as .csv",
    ".xlsx": "export the relevant sheet as .csv",
}


class _DocxSkipError(ValueError):
    """Signal a malformed .docx that should be skipped, not treated as fatal."""


def extract_file(path: Path, root: Path | None = None) -> dict:
    """
    Extract one file. Never raises: failures are reported in the result.

    status is "success", "skipped" (unsupported or no text) or "error".
    ``source`` is the path relative to ``root`` so files with the same name in
    different folders stay distinguishable.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    result = {
        "status": "success",
        "source": path.relative_to(root).as_posix() if root else path.name,
        "filename": path.name,
        "file_type": suffix,
        "title": None,
        "page_count": None,
        "row_count": None,
        "column_count": None,
        "text": "",
        "message": None,
    }

    extractor = EXTRACTORS.get(suffix)

    if extractor is None:
        message = f"unsupported file type '{suffix}'"

        if suffix in _UNSUPPORTED_HINTS:
            message += f" ({_UNSUPPORTED_HINTS[suffix]})"

        result.update(status="skipped", message=message)
        return result

    try:
        result.update(extractor(path))
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"

        if suffix == ".docx":
            if isinstance(exc, _DocxSkipError):
                result.update(status="skipped", message=str(exc))
                return result

            result.update(status="error", message=f"invalid .docx ({message})")
            return result

        result.update(status="error", message=message)
        return result

    if not result["text"].strip():
        result.update(
            status="skipped",
            message="no extractable text (empty or scanned file?)",
        )

    return result


def _is_ignored(path: Path) -> bool:
    """Hidden files and Office lock files are never documents."""
    return path.name.startswith((".", "~$"))


def extract_directory(directory: str | Path) -> list[dict]:
    """Extract every file under a directory, recursively, in a stable order."""
    directory = Path(directory)

    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")

    return [
        extract_file(path, root=directory)
        for path in sorted(directory.rglob("*"))
        if path.is_file() and not _is_ignored(path)
    ]