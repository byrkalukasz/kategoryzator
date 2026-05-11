from datetime import datetime, timezone

from api.services.db_core import connect, init_db, sanitize_company_id


def register_llm_usage(
    company_id: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int | None = None,
    request_count: int = 1,
    usage_month: str | None = None,
) -> dict:
    init_db()
    cid = sanitize_company_id(company_id)

    inp = max(0, int(input_tokens or 0))
    out = max(0, int(output_tokens or 0))
    total = max(0, int(total_tokens if total_tokens is not None else inp + out))
    req = max(0, int(request_count or 0))
    month = usage_month or datetime.now(timezone.utc).strftime("%Y-%m")
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO llm_usage_monthly (
                company_id, usage_month, requests_count,
                input_tokens, output_tokens, total_tokens, last_request_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(company_id, usage_month)
            DO UPDATE SET
                requests_count = llm_usage_monthly.requests_count + excluded.requests_count,
                input_tokens = llm_usage_monthly.input_tokens + excluded.input_tokens,
                output_tokens = llm_usage_monthly.output_tokens + excluded.output_tokens,
                total_tokens = llm_usage_monthly.total_tokens + excluded.total_tokens,
                last_request_at = excluded.last_request_at
            """,
            (cid, month, req, inp, out, total, now_iso),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT company_id, usage_month, requests_count,
                   input_tokens, output_tokens, total_tokens, last_request_at
            FROM llm_usage_monthly
            WHERE company_id = ? AND usage_month = ?
            """,
            (cid, month),
        ).fetchone()
    finally:
        conn.close()

    return {
        "company_id": row["company_id"],
        "usage_month": row["usage_month"],
        "requests_count": int(row["requests_count"]),
        "input_tokens": int(row["input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "total_tokens": int(row["total_tokens"]),
        "last_request_at": row["last_request_at"],
    }


def get_llm_usage(company_id: str, usage_month: str | None = None) -> dict:
    init_db()
    cid = sanitize_company_id(company_id)
    month = usage_month or datetime.now(timezone.utc).strftime("%Y-%m")

    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT company_id, usage_month, requests_count,
                   input_tokens, output_tokens, total_tokens, last_request_at
            FROM llm_usage_monthly
            WHERE company_id = ? AND usage_month = ?
            """,
            (cid, month),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return {
            "company_id": cid,
            "usage_month": month,
            "requests_count": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "last_request_at": None,
        }

    return {
        "company_id": row["company_id"],
        "usage_month": row["usage_month"],
        "requests_count": int(row["requests_count"]),
        "input_tokens": int(row["input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "total_tokens": int(row["total_tokens"]),
        "last_request_at": row["last_request_at"],
    }


def list_llm_usage_clients(
    usage_month: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    init_db()
    month = usage_month or datetime.now(timezone.utc).strftime("%Y-%m")
    limit = min(max(1, int(limit)), 500)
    offset = max(0, int(offset))

    conn = connect()
    try:
        count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM llm_usage_monthly WHERE usage_month = ?",
            (month,),
        ).fetchone()
        total_clients = int(count_row["cnt"])

        rows = conn.execute(
            """
            SELECT company_id, usage_month, requests_count,
                   input_tokens, output_tokens, total_tokens, last_request_at
            FROM llm_usage_monthly
            WHERE usage_month = ?
            ORDER BY total_tokens DESC, requests_count DESC, company_id ASC
            LIMIT ? OFFSET ?
            """,
            (month, limit, offset),
        ).fetchall()

        items = [
            {
                "company_id": row["company_id"],
                "usage_month": row["usage_month"],
                "requests_count": int(row["requests_count"]),
                "input_tokens": int(row["input_tokens"]),
                "output_tokens": int(row["output_tokens"]),
                "total_tokens": int(row["total_tokens"]),
                "last_request_at": row["last_request_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()

    return {
        "usage_month": month,
        "total_clients": total_clients,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


def get_llm_usage_report_summary(usage_month: str | None = None) -> dict:
    init_db()
    month = usage_month or datetime.now(timezone.utc).strftime("%Y-%m")

    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_clients,
                COALESCE(SUM(requests_count), 0) AS requests_count,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM llm_usage_monthly
            WHERE usage_month = ?
            """,
            (month,),
        ).fetchone()
    finally:
        conn.close()

    return {
        "usage_month": month,
        "total_clients": int(row["total_clients"]),
        "requests_count": int(row["requests_count"]),
        "input_tokens": int(row["input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "total_tokens": int(row["total_tokens"]),
    }
