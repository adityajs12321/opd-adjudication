import json
import os
from typing import Optional

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

_pool: pool.SimpleConnectionPool | None = None


def get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 10, dsn=os.environ["DATABASE_URL"])
    return _pool


def _conn():
    return get_pool().getconn()


def _release(conn):
    get_pool().putconn(conn)


def init_db():
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    member_id   TEXT PRIMARY KEY,
                    name        TEXT NOT NULL,
                    join_date   DATE NOT NULL,
                    is_active   BOOLEAN DEFAULT TRUE,
                    relationship TEXT DEFAULT 'employee'
                );

                CREATE TABLE IF NOT EXISTS claims (
                    claim_id        TEXT PRIMARY KEY,
                    member_id       TEXT NOT NULL,
                    treatment_date  DATE,
                    bill_number     TEXT,
                    hospital_name   TEXT,
                    total_claimed   FLOAT DEFAULT 0,
                    approved_amount FLOAT DEFAULT 0,
                    decision        TEXT,
                    policy_year     INT NOT NULL,
                    submitted_at    TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS claim_documents (
                    id             SERIAL PRIMARY KEY,
                    claim_id       TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
                    document_type  TEXT NOT NULL,
                    extracted_data JSONB,
                    uploaded_at    TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_claims_member_year
                    ON claims(member_id, policy_year);
                CREATE INDEX IF NOT EXISTS idx_claims_duplicate
                    ON claims(member_id, treatment_date, hospital_name);
            """)
        conn.commit()
    finally:
        _release(conn)


# ── Members ───────────────────────────────────────────────────────────────────

def _serialize_member(row) -> dict:
    d = dict(row)
    if d.get("join_date") and not isinstance(d["join_date"], str):
        d["join_date"] = d["join_date"].isoformat()
    return d


def get_member(member_id: str) -> Optional[dict]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM members WHERE member_id = %s", (member_id,))
            row = cur.fetchone()
            return _serialize_member(row) if row else None
    finally:
        _release(conn)


def create_member(member_id: str, name: str, join_date: str, relationship: str = "employee") -> dict:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO members (member_id, name, join_date, relationship)
                   VALUES (%s, %s, %s::date, %s)
                   ON CONFLICT (member_id) DO UPDATE SET
                       name         = EXCLUDED.name,
                       join_date    = EXCLUDED.join_date,
                       relationship = EXCLUDED.relationship,
                       is_active    = TRUE
                   RETURNING *""",
                (member_id, name, join_date, relationship),
            )
            conn.commit()
            return _serialize_member(cur.fetchone())
    finally:
        _release(conn)


# ── Claims ────────────────────────────────────────────────────────────────────

def get_annual_spend(member_id: str, policy_year: int) -> float:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(SUM(approved_amount), 0)
                   FROM claims
                   WHERE member_id = %s
                     AND policy_year = %s
                     AND decision IN ('APPROVED', 'PARTIAL')""",
                (member_id, policy_year),
            )
            return float(cur.fetchone()[0])
    finally:
        _release(conn)


def check_duplicate(
    member_id: str,
    bill_number: str,
    treatment_date: str,
    hospital_name: str,
) -> bool:
    """
    Duplicate = same member with either:
      - the same non-empty bill number, OR
      - the same treatment date + hospital name
    """
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM claims
                   WHERE member_id = %s
                     AND (
                           (bill_number IS NOT NULL AND bill_number <> '' AND bill_number = %s)
                        OR (treatment_date IS NOT NULL AND treatment_date = %s::date
                            AND hospital_name ILIKE %s)
                     )
                   LIMIT 1""",
                (
                    member_id,
                    bill_number or "",
                    treatment_date or None,
                    hospital_name or "",
                ),
            )
            return cur.fetchone() is not None
    finally:
        _release(conn)


def save_claim(
    claim_id: str,
    member_id: str,
    decision: str,
    approved_amount: float,
    total_claimed: float,
    treatment_date: str,
    bill_number: str,
    hospital_name: str,
    policy_year: int,
):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO claims
                       (claim_id, member_id, treatment_date, bill_number, hospital_name,
                        total_claimed, approved_amount, decision, policy_year)
                   VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (claim_id) DO UPDATE SET
                       decision        = EXCLUDED.decision,
                       approved_amount = EXCLUDED.approved_amount""",
                (
                    claim_id, member_id,
                    treatment_date or None,
                    bill_number or None,
                    hospital_name or None,
                    total_claimed, approved_amount,
                    decision, policy_year,
                ),
            )
        conn.commit()
    finally:
        _release(conn)


def save_claim_documents(claim_id: str, documents: dict):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            for doc_type, data in documents.items():
                if data is not None:
                    cur.execute(
                        """INSERT INTO claim_documents (claim_id, document_type, extracted_data)
                           VALUES (%s, %s, %s)""",
                        (claim_id, doc_type, json.dumps(data)),
                    )
        conn.commit()
    finally:
        _release(conn)
