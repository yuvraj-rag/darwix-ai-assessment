from pathlib import Path
import tempfile

from tests.conftest import (
    ELIGIBILITY_MD,
    DOCUMENTS_HTML,
    PARTNER_HTML,
    LIMITS_CSV,
    REPAYMENT_LINES,
    fake_embed,
)
from app import pipeline, vector_store
import pymupdf


def setup_corpus():
    tmp = Path(tempfile.mkdtemp())
    raw = tmp / 'raw'
    raw.mkdir()
    (raw / 'nested').mkdir()
    (raw / 'eligibility_criteria.md').write_text(ELIGIBILITY_MD, encoding='utf-8')
    (raw / 'eligibility_criteria_copy.md').write_text(ELIGIBILITY_MD, encoding='utf-8')
    (raw / 'eligibility_v2.md').write_text(
        ELIGIBILITY_MD.replace('700', '720').replace('1.2', '1.3'),
        encoding='utf-8',
    )
    (raw / 'documents_required.html').write_text(DOCUMENTS_HTML, encoding='utf-8')
    (raw / 'nested' / 'partner_website.html').write_text(PARTNER_HTML, encoding='utf-8')
    (raw / 'loan_limits_table.csv').write_text(LIMITS_CSV, encoding='utf-8')

    pdf = pymupdf.open()
    page = pdf.new_page()
    y = 72
    for line in REPAYMENT_LINES:
        page.insert_text((72, y), line)
        y += 18
    pdf.save(raw / 'repayment_policy.pdf')
    pdf.close()

    blank = pymupdf.open()
    blank.new_page()
    blank.save(raw / 'scanned.pdf')
    blank.close()
    (raw / 'corrupt.pdf').write_bytes(b'not a pdf at all')
    (raw / 'notes.docx').write_bytes(b'PK\x03\x04')
    (raw / '.DS_Store').write_bytes(b'junk')

    out = tmp / 'processed'
    db = tmp / 'chroma'
    pipeline.ingest(raw, out)
    vector_store.build_index(out / 'chunks.json', db, embed_fn=fake_embed)
    return db, out, raw


if __name__ == '__main__':
    db, _, _ = setup_corpus()
    collection = vector_store.get_collection(db)
    queries = [
        'minimum annual turnover',
        'what is the prepayment charge',
        'which documents do I need to submit',
        'term loan maximum amount',
        'what is the travel reimbursement policy',
        'customer CUST-2024-0042',
        'employee handbook leave policy',
        'how much is the claim reimbursement'
    ]
    for q in queries:
        hits = vector_store.retrieve(q, top_k=5, collection=collection, embed_fn=fake_embed)
        print(f'QUERY: {q}')
        for hit in hits[:3]:
            print('  -', hit['source'], 'score=', hit['score'], 'category=', hit['category'])
        print()
