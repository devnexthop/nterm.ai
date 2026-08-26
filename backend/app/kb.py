from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import KbDocument


def ingest(db: Session, *, title: str, body: str, source: str = "paste", vendor: str = "", customer_id: int | None = None) -> KbDocument:
    row = KbDocument(title=title[:300], body=body, source=source, vendor=vendor, customer_id=customer_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        db.execute(
            text("INSERT INTO kb_fts (title, body, doc_id) VALUES (:t, :b, :id)"),
            {"t": row.title, "b": row.body, "id": str(row.id)},
        )
        db.commit()
    except Exception:
        db.rollback()
    return row


def search(db: Session, query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    rows: list[KbDocument] = []
    try:
        hits = db.execute(
            text("SELECT doc_id FROM kb_fts WHERE kb_fts MATCH :q LIMIT :n"),
            {"q": q, "n": limit},
        ).fetchall()
        ids = [int(h[0]) for h in hits if str(h[0]).isdigit()]
        if ids:
            rows = db.query(KbDocument).filter(KbDocument.id.in_(ids)).all()
    except Exception:
        db.rollback()
    if not rows:
        like = f"%{q}%"
        rows = (
            db.query(KbDocument)
            .filter((KbDocument.body.ilike(like)) | (KbDocument.title.ilike(like)))
            .order_by(KbDocument.id.desc())
            .limit(limit)
            .all()
        )
    return [
        {
            "id": r.id,
            "title": r.title,
            "source": r.source,
            "vendor": r.vendor,
            "customer_id": r.customer_id,
            "snippet": r.body[:800],
        }
        for r in rows
    ]


def fingerprint(chunks: list[dict]) -> str:
    return ",".join(str(c.get("id")) for c in chunks)
