from datetime import datetime, timezone

from api.services.db_core import (
    cache_ttl_seconds,
    connect,
    default_ai_threshold,
    default_company_llm_enabled,
    default_exact_threshold,
    init_db,
    sanitize_company_id,
)

_CONFIG_CACHE: dict[str, tuple[dict, float]] = {}


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def get_company_config(company_id: str) -> dict:
    init_db()
    cid = sanitize_company_id(company_id)
    now = _now_ts()

    cached = _CONFIG_CACHE.get(cid)
    if cached is not None:
        payload, ts = cached
        if now - ts <= cache_ttl_seconds():
            return payload

    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, company_id, confidence_exact, confidence_ai, llm_enabled
            FROM company_prediction_config
            WHERE company_id = ?
            """,
            (cid,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        payload = {
            "id": None,
            "company_id": cid,
            "confidence_exact": float(default_exact_threshold()),
            "confidence_ai": float(default_ai_threshold()),
            "llm_enabled": bool(default_company_llm_enabled()),
            "source": "default",
        }
    else:
        payload = {
            "id": int(row["id"]),
            "company_id": row["company_id"],
            "confidence_exact": float(row["confidence_exact"]),
            "confidence_ai": float(row["confidence_ai"]),
            "llm_enabled": bool(row["llm_enabled"]),
            "source": "company",
        }

    _CONFIG_CACHE[cid] = (payload, now)
    return payload


def upsert_company_config(
    company_id: str,
    confidence_exact: float,
    confidence_ai: float,
    llm_enabled: bool | None = None,
) -> dict:
    init_db()
    cid = sanitize_company_id(company_id)
    exact = float(confidence_exact)
    ai = float(confidence_ai)

    if exact < 0.0 or exact > 1.0:
        raise ValueError("confidence_exact musi byc w zakresie [0, 1].")
    if ai < 0.0 or ai > 1.0:
        raise ValueError("confidence_ai musi byc w zakresie [0, 1].")
    if ai > exact:
        raise ValueError("confidence_ai nie moze byc wieksze od confidence_exact.")

    llm_enabled_value = (
        1 if bool(llm_enabled)
        else 0 if llm_enabled is not None
        else None
    )

    conn = connect()
    try:
        existing = conn.execute(
            "SELECT llm_enabled FROM company_prediction_config WHERE company_id = ?",
            (cid,),
        ).fetchone()
        if llm_enabled_value is None:
            if existing is not None:
                llm_enabled_value = int(existing["llm_enabled"])
            else:
                llm_enabled_value = 1 if default_company_llm_enabled() else 0

        conn.execute(
            """
            INSERT INTO company_prediction_config (company_id, confidence_exact, confidence_ai, llm_enabled)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(company_id)
            DO UPDATE SET confidence_exact = excluded.confidence_exact,
                          confidence_ai = excluded.confidence_ai,
                          llm_enabled = excluded.llm_enabled
            """,
            (cid, exact, ai, llm_enabled_value),
        )
        conn.commit()

        row = conn.execute(
            """
            SELECT id, company_id, confidence_exact, confidence_ai, llm_enabled
            FROM company_prediction_config
            WHERE company_id = ?
            """,
            (cid,),
        ).fetchone()
    finally:
        conn.close()

    payload = {
        "id": int(row["id"]),
        "company_id": row["company_id"],
        "confidence_exact": float(row["confidence_exact"]),
        "confidence_ai": float(row["confidence_ai"]),
        "llm_enabled": bool(row["llm_enabled"]),
        "source": "company",
    }
    _CONFIG_CACHE[cid] = (payload, _now_ts())
    return payload
