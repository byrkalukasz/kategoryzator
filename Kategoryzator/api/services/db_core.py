import hashlib
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
EMBEDDING_DIM = int(os.environ.get("BOOKED_EMBEDDING_DIM", "128"))
TARGET_SCHEMA_VERSION = 4
_SCHEMA_READY_BY_DB_PATH: set[str] = set()


def resolve_path(*parts: str) -> str:
    return str(BASE_DIR.joinpath(*parts))


def db_path() -> str:
    path = os.environ.get("BOOKED_DB_PATH", resolve_path("logs", "booked_invoices.db"))
    if not os.path.isabs(path):
        path = resolve_path(path)
    return path


def similarity_threshold() -> float:
    return float(os.environ.get("BOOKED_SIMILARITY_THRESHOLD", "0.92"))


def default_exact_threshold() -> float:
    return float(os.environ.get("DEFAULT_CONFIDENCE_EXACT", str(similarity_threshold())))


def default_ai_threshold() -> float:
    return float(os.environ.get("DEFAULT_CONFIDENCE_AI", "0.75"))


def cache_ttl_seconds() -> int:
    return int(os.environ.get("COMPANY_CONFIG_CACHE_TTL_SECONDS", "300"))


def default_company_llm_enabled() -> bool:
    value = os.environ.get("DEFAULT_COMPANY_LLM_ENABLED", "0")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def sanitize_company_id(company_id_raw) -> str:
    cid = str(company_id_raw).strip()
    if cid.endswith(".0"):
        cid = cid[:-2]
    return cid


def embedding_for_text(text: str) -> list[float]:
    norm = normalize_text(text)
    if not norm:
        return [0.0] * EMBEDDING_DIM

    vec = [0.0] * EMBEDDING_DIM
    for tok in norm.split():
        digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=16).digest()
        idx = int.from_bytes(digest[:8], "little") % EMBEDDING_DIM
        sign = 1.0 if (digest[8] & 1) == 0 else -1.0
        vec[idx] += sign

    norm_l2 = math.sqrt(sum(v * v for v in vec))
    if norm_l2 <= 0.0:
        return vec
    return [v / norm_l2 for v in vec]


def embedding_to_json(vec: list[float]) -> str:
    return json.dumps(vec, ensure_ascii=False)


def embedding_from_json(value: str | None) -> list[float]:
    if not value:
        return [0.0] * EMBEDDING_DIM
    try:
        data = json.loads(value)
        if not isinstance(data, list):
            return [0.0] * EMBEDDING_DIM
        if len(data) < EMBEDDING_DIM:
            data = data + [0.0] * (EMBEDDING_DIM - len(data))
        return [float(x) for x in data[:EMBEDDING_DIM]]
    except Exception:
        return [0.0] * EMBEDDING_DIM


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2:
        return 0.0
    n = min(len(v1), len(v2))
    return float(sum(v1[i] * v2[i] for i in range(n)))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _current_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    return int(row["v"]) if row else 0


def _mark_migration(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES(?, ?)",
        (version, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
    )


def _migration_1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS booked_invoices (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at               TEXT    NOT NULL,
            company_id               TEXT    NOT NULL,
            accounting_type          TEXT    NOT NULL,
            typ_pozycji              TEXT    NOT NULL,
            nazwa                    TEXT    NOT NULL,
            nazwa_normalized         TEXT    NOT NULL,
            embedding_json           TEXT    NOT NULL DEFAULT '[]',
            selected_prediction_json TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_booked_lookup
            ON booked_invoices (company_id, accounting_type, typ_pozycji);

        CREATE INDEX IF NOT EXISTS idx_booked_created_at
            ON booked_invoices (created_at DESC);

        CREATE VIRTUAL TABLE IF NOT EXISTS booked_invoices_fts
            USING fts5(
                nazwa_normalized,
                content=booked_invoices,
                content_rowid=id,
                tokenize='unicode61 remove_diacritics 2'
            );

        CREATE TRIGGER IF NOT EXISTS booked_ai
            AFTER INSERT ON booked_invoices BEGIN
                INSERT INTO booked_invoices_fts(rowid, nazwa_normalized)
                    VALUES (new.id, new.nazwa_normalized);
            END;

        CREATE TRIGGER IF NOT EXISTS booked_ad
            AFTER DELETE ON booked_invoices BEGIN
                INSERT INTO booked_invoices_fts(booked_invoices_fts, rowid, nazwa_normalized)
                    VALUES ('delete', old.id, old.nazwa_normalized);
            END;

        CREATE TRIGGER IF NOT EXISTS booked_au
            AFTER UPDATE ON booked_invoices BEGIN
                INSERT INTO booked_invoices_fts(booked_invoices_fts, rowid, nazwa_normalized)
                    VALUES ('delete', old.id, old.nazwa_normalized);
                INSERT INTO booked_invoices_fts(rowid, nazwa_normalized)
                    VALUES (new.id, new.nazwa_normalized);
            END;
        """
    )


def _migration_2(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_prediction_config (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id       TEXT NOT NULL UNIQUE,
            confidence_exact REAL NOT NULL,
            confidence_ai    REAL NOT NULL,
            llm_enabled      INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cfg_cols = {row["name"] for row in conn.execute("PRAGMA table_info(company_prediction_config)").fetchall()}
    if "llm_enabled" not in cfg_cols:
        conn.execute("ALTER TABLE company_prediction_config ADD COLUMN llm_enabled INTEGER NOT NULL DEFAULT 0")


def _migration_3(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_usage_monthly (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id      TEXT NOT NULL,
            usage_month     TEXT NOT NULL,
            requests_count  INTEGER NOT NULL DEFAULT 0,
            input_tokens    INTEGER NOT NULL DEFAULT 0,
            output_tokens   INTEGER NOT NULL DEFAULT 0,
            total_tokens    INTEGER NOT NULL DEFAULT 0,
            last_request_at TEXT NOT NULL,
            UNIQUE(company_id, usage_month)
        )
        """
    )


def _migration_4(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(booked_invoices)").fetchall()}
    if "embedding_json" not in cols:
        conn.execute("ALTER TABLE booked_invoices ADD COLUMN embedding_json TEXT NOT NULL DEFAULT '[]'")

    conn.execute("INSERT INTO booked_invoices_fts(booked_invoices_fts) VALUES ('rebuild')")

    rows_without_embedding = conn.execute(
        "SELECT id, nazwa_normalized FROM booked_invoices WHERE embedding_json = '[]' OR embedding_json = '' OR embedding_json IS NULL"
    ).fetchall()
    for row in rows_without_embedding:
        emb = embedding_for_text(row["nazwa_normalized"])
        conn.execute(
            "UPDATE booked_invoices SET embedding_json = ? WHERE id = ?",
            (embedding_to_json(emb), row["id"]),
        )


_MIGRATIONS = [
    (1, _migration_1),
    (2, _migration_2),
    (3, _migration_3),
    (4, _migration_4),
]


def _run_migrations(conn: sqlite3.Connection) -> None:
    _ensure_migrations_table(conn)
    current = _current_schema_version(conn)
    for version, migration_fn in _MIGRATIONS:
        if version > current:
            migration_fn(conn)
            _mark_migration(conn, version)


def init_db() -> None:
    path = db_path()
    if path in _SCHEMA_READY_BY_DB_PATH and os.path.exists(path):
        conn = connect()
        try:
            _ensure_migrations_table(conn)
            if _current_schema_version(conn) >= TARGET_SCHEMA_VERSION:
                return
        finally:
            conn.close()
        _SCHEMA_READY_BY_DB_PATH.discard(path)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    conn = connect()
    try:
        _run_migrations(conn)
        conn.commit()
        _SCHEMA_READY_BY_DB_PATH.add(path)
    finally:
        conn.close()
