import json
import sqlite3
from datetime import datetime, timezone
from difflib import SequenceMatcher

from api.services.db_core import (
    connect,
    cosine_similarity,
    embedding_for_text,
    embedding_from_json,
    embedding_to_json,
    init_db,
    normalize_text,
    sanitize_company_id,
    similarity_threshold,
)


def store_invoice(
    nazwa: str,
    typ_pozycji: str,
    company_id: str,
    accounting_type: str,
    selected_prediction: dict,
) -> int:
    init_db()
    conn = connect()
    try:
        normalized = normalize_text(nazwa)
        embedding_json = embedding_to_json(embedding_for_text(normalized))
        cursor = conn.execute(
            """
            INSERT INTO booked_invoices
                (created_at, company_id, accounting_type, typ_pozycji,
                 nazwa, nazwa_normalized, embedding_json, selected_prediction_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                company_id,
                accounting_type,
                typ_pozycji,
                nazwa,
                normalized,
                embedding_json,
                json.dumps(selected_prediction, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def _fts_query(needle: str) -> str:
    tokens = needle.split()
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def _base_candidates(
    conn: sqlite3.Connection,
    needle: str,
    typ_pozycji: str,
    company_id: str,
    accounting_type: str,
) -> list[sqlite3.Row]:
    rows = None
    if needle.strip():
        try:
            rows = conn.execute(
                """
                SELECT b.id, b.created_at, b.company_id, b.accounting_type,
                       b.typ_pozycji, b.nazwa, b.nazwa_normalized, b.embedding_json,
                       b.selected_prediction_json
                FROM booked_invoices b
                JOIN booked_invoices_fts f ON f.rowid = b.id
                WHERE f.booked_invoices_fts MATCH ?
                  AND b.accounting_type  = ?
                  AND b.typ_pozycji      = ?
                  AND b.company_id       = ?
                ORDER BY rank
                LIMIT 80
                """,
                (_fts_query(needle), accounting_type, typ_pozycji, company_id),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = None

    if not rows:
        rows = conn.execute(
            """
            SELECT id, created_at, company_id, accounting_type,
                   typ_pozycji, nazwa, nazwa_normalized, embedding_json, selected_prediction_json
            FROM booked_invoices
            WHERE accounting_type = ?
              AND typ_pozycji     = ?
              AND company_id      = ?
            ORDER BY id DESC
            LIMIT 300
            """,
            (accounting_type, typ_pozycji, company_id),
        ).fetchall()
    return list(rows)


def find_similar_candidates(
    nazwa: str,
    typ_pozycji: str,
    company_id: str,
    accounting_type: str,
    limit: int = 3,
) -> list[dict]:
    init_db()
    needle = normalize_text(nazwa)
    q_emb = embedding_for_text(needle)

    conn = connect()
    try:
        rows = _base_candidates(conn, needle, typ_pozycji, company_id, accounting_type)
        scored = []
        for row in rows:
            text_score = SequenceMatcher(None, needle, row["nazwa_normalized"]).ratio()
            emb_score = max(0.0, cosine_similarity(q_emb, embedding_from_json(row["embedding_json"])))
            hybrid_score = 0.55 * text_score + 0.45 * emb_score
            scored.append((hybrid_score, text_score, emb_score, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: max(1, int(limit))]

        result = []
        for hybrid_score, text_score, emb_score, row in top:
            result.append(
                {
                    "id": int(row["id"]),
                    "created_at": row["created_at"],
                    "nazwa": row["nazwa"],
                    "similarity": round(float(hybrid_score), 4),
                    "text_similarity": round(float(text_score), 4),
                    "embedding_similarity": round(float(emb_score), 4),
                    "selected_prediction": json.loads(row["selected_prediction_json"]),
                }
            )
        return result
    finally:
        conn.close()


def find_similar(
    nazwa: str,
    typ_pozycji: str,
    company_id: str,
    accounting_type: str,
    threshold: float | None = None,
) -> dict | None:
    if threshold is None:
        threshold = similarity_threshold()

    candidates = find_similar_candidates(
        nazwa=nazwa,
        typ_pozycji=typ_pozycji,
        company_id=company_id,
        accounting_type=accounting_type,
        limit=1,
    )
    if not candidates:
        return None
    best = candidates[0]
    if best["similarity"] < threshold:
        return None
    return best


def list_history(
    company_id: str | None = None,
    accounting_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    limit = min(limit, 200)
    init_db()
    conn = connect()
    try:
        where_clauses: list[str] = []
        params: list = []

        if company_id is not None:
            where_clauses.append("company_id = ?")
            params.append(sanitize_company_id(company_id))
        if accounting_type is not None:
            where_clauses.append("accounting_type = ?")
            params.append(accounting_type.strip().lower())

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS cnt FROM booked_invoices {where_sql}", params
            ).fetchone()["cnt"]
        )

        rows = conn.execute(
            f"""
            SELECT id, created_at, company_id, accounting_type, typ_pozycji,
                   nazwa, selected_prediction_json
            FROM booked_invoices
            {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "id": int(r["id"]),
                    "created_at": r["created_at"],
                    "company_id": r["company_id"],
                    "accounting_type": r["accounting_type"],
                    "typ_pozycji": r["typ_pozycji"],
                    "nazwa": r["nazwa"],
                    "selected_prediction": json.loads(r["selected_prediction_json"]),
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


def delete_invoice(booking_id: int) -> bool:
    init_db()
    conn = connect()
    try:
        cursor = conn.execute("DELETE FROM booked_invoices WHERE id = ?", (booking_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
