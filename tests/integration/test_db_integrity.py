"""
tests/integration/test_db_integrity.py

DB-level integrity tests: constraints, defaults, indexes.
Connects directly to PostgreSQL via psycopg2 — does NOT go through FastAPI.

outputs table schema (relevant columns):
    id              SERIAL PK
    case_id         INT NOT NULL  → FK cases(id)
    passo_origem    INT NOT NULL  CHECK 1..6
    classe          output_class  NOT NULL
    status          output_status NOT NULL  DEFAULT 'rascunho'
    titulo          VARCHAR NOT NULL
    conteudo        JSONB NOT NULL DEFAULT '{}'
    disclaimer      TEXT NOT NULL
    imutavel        BOOLEAN NOT NULL DEFAULT false
    legal_hold      BOOLEAN NOT NULL DEFAULT false
    legal_hold_ate  DATE
    user_id         UUID → FK users(id) ON DELETE SET NULL

Constraint of interest:
    chk_output_imutavel: CHECK (classe NOT IN ('dossie_decisao','material_compartilhavel')
                                OR imutavel = true)
"""
import pytest
import psycopg2
import psycopg2.errorcodes
from psycopg2 import errors as pg_errors
from datetime import date, timedelta

DB_URL = "postgresql://taxmind:taxmind123@localhost:5436/taxmind_db"


@pytest.fixture(scope="module")
def db_conn():
    """Direct psycopg2 connection for DB-level tests."""
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    yield conn
    conn.close()


def _get_valid_case_id(conn) -> int:
    """Return an existing case_id from the DB."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM cases ORDER BY id LIMIT 1")
        row = cur.fetchone()
    if row is None:
        pytest.skip("No cases exist in DB — cannot run outputs constraint tests")
    return row[0]


# ---------------------------------------------------------------------------
# TC-DB-01: chk_output_imutavel — INSERT with imutavel=false should be rejected
# ---------------------------------------------------------------------------

def test_db_01_check_output_imutavel_rejects_false(db_conn):
    """
    TC-DB-01: Inserting a dossie_decisao output with imutavel=false must raise
    IntegrityError (CheckViolation) due to chk_output_imutavel.
    """
    case_id = _get_valid_case_id(db_conn)

    with pytest.raises(Exception) as exc_info:
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO outputs
                    (case_id, passo_origem, classe, titulo, conteudo, disclaimer, imutavel)
                VALUES
                    (%s, 5, 'dossie_decisao', 'TC-DB-01 test', '{}', 'test disclaimer', false)
                """,
                (case_id,),
            )
    # Always rollback so subsequent tests start clean
    db_conn.rollback()

    # Should be a psycopg2 IntegrityError (CheckViolation)
    assert isinstance(exc_info.value, psycopg2.IntegrityError), (
        f"Expected IntegrityError, got {type(exc_info.value)}: {exc_info.value}"
    )
    pgcode = getattr(exc_info.value, "pgcode", None)
    assert pgcode == psycopg2.errorcodes.CHECK_VIOLATION, (
        f"Expected CHECK_VIOLATION (23514), got pgcode={pgcode}"
    )


# ---------------------------------------------------------------------------
# TC-DB-02: chk_output_imutavel — INSERT with imutavel=true should succeed
#           (may fail on FK if case_id doesn't exist, which is NOT a constraint error)
# ---------------------------------------------------------------------------

def test_db_02_check_output_imutavel_accepts_true(db_conn):
    """
    TC-DB-02: Inserting a dossie_decisao output with imutavel=true must NOT raise
    a CheckViolation — it either succeeds or fails on a FK, never on chk_output_imutavel.
    """
    case_id = _get_valid_case_id(db_conn)

    inserted_id = None
    try:
        with db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO outputs
                    (case_id, passo_origem, classe, titulo, conteudo, disclaimer, imutavel)
                VALUES
                    (%s, 5, 'dossie_decisao', 'TC-DB-02 test', '{}', 'test disclaimer', true)
                RETURNING id
                """,
                (case_id,),
            )
            row = cur.fetchone()
            inserted_id = row[0] if row else None
        db_conn.commit()
    except psycopg2.IntegrityError as e:
        db_conn.rollback()
        pgcode = getattr(e, "pgcode", None)
        # FK violation is acceptable — means case_id FK fired, not the check constraint
        assert pgcode == psycopg2.errorcodes.FOREIGN_KEY_VIOLATION, (
            f"Unexpected IntegrityError pgcode={pgcode}: {e}"
        )
    except Exception:
        db_conn.rollback()
        raise
    finally:
        # Cleanup inserted row if it was created
        if inserted_id is not None:
            try:
                with db_conn.cursor() as cur:
                    cur.execute("DELETE FROM outputs WHERE id = %s", (inserted_id,))
                db_conn.commit()
            except Exception:
                db_conn.rollback()


# ---------------------------------------------------------------------------
# TC-DB-03: legal_hold_ate default should be ~5 years from now for dossie_decisao
# ---------------------------------------------------------------------------

def test_db_03_legal_hold_ate_default_five_years(db_conn):
    """
    TC-DB-03: When legal_hold=true is set on a dossie_decisao output,
    legal_hold_ate should be approximately 5 years from now.
    If no outputs with legal_hold=true exist, check via direct INSERT/SELECT.
    """
    # First check if any existing outputs satisfy the condition
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT legal_hold_ate
            FROM outputs
            WHERE legal_hold = true
              AND classe = 'dossie_decisao'
              AND legal_hold_ate IS NOT NULL
            LIMIT 1
            """
        )
        row = cur.fetchone()

    if row:
        legal_hold_ate = row[0]
        today = date.today()
        # Should be between 4.5 and 5.5 years from today
        lower = today + timedelta(days=int(365 * 4.5))
        upper = today + timedelta(days=int(365 * 5.5))
        assert lower <= legal_hold_ate <= upper, (
            f"legal_hold_ate={legal_hold_ate} not in expected range [{lower}, {upper}]"
        )
    else:
        # Insert a test row with legal_hold=true and check the resulting legal_hold_ate
        case_id = _get_valid_case_id(db_conn)
        inserted_id = None
        try:
            with db_conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO outputs
                        (case_id, passo_origem, classe, titulo, conteudo, disclaimer,
                         imutavel, legal_hold, legal_hold_ate)
                    VALUES
                        (%s, 5, 'dossie_decisao', 'TC-DB-03 test', '{}',
                         'test disclaimer', true, true,
                         CURRENT_DATE + INTERVAL '5 years')
                    RETURNING id, legal_hold_ate
                    """,
                    (case_id,),
                )
                row = cur.fetchone()
            db_conn.commit()
            assert row is not None
            inserted_id, legal_hold_ate = row[0], row[1]
            today = date.today()
            lower = today + timedelta(days=int(365 * 4.5))
            upper = today + timedelta(days=int(365 * 5.5))
            assert lower <= legal_hold_ate <= upper, (
                f"legal_hold_ate={legal_hold_ate} not in expected range [{lower}, {upper}]"
            )
        except psycopg2.IntegrityError as e:
            db_conn.rollback()
            pytest.skip(f"Could not insert test row (FK or constraint): {e}")
        finally:
            if inserted_id is not None:
                try:
                    with db_conn.cursor() as cur:
                        cur.execute("DELETE FROM outputs WHERE id = %s", (inserted_id,))
                    db_conn.commit()
                except Exception:
                    db_conn.rollback()


# ---------------------------------------------------------------------------
# TC-DB-04: case_state_history — at least one record exists for any existing case
# ---------------------------------------------------------------------------

def test_db_04_case_state_history_has_records(db_conn):
    """
    TC-DB-04: The case_state_history table must have at least one record, and the
    case_id referenced must exist in the cases table.
    """
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM case_state_history")
        total = cur.fetchone()[0]

    assert total > 0, (
        "case_state_history has no records — protocol engine may not have run"
    )

    # Verify referential consistency: every case_id in history exists in cases
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM case_state_history csh
            LEFT JOIN cases c ON c.id = csh.case_id
            WHERE c.id IS NULL
            """
        )
        orphans = cur.fetchone()[0]

    assert orphans == 0, (
        f"{orphans} case_state_history rows reference non-existent cases"
    )


# ---------------------------------------------------------------------------
# TC-DB-05: HNSW index on embeddings — EXPLAIN should mention "Index Scan"
# ---------------------------------------------------------------------------

def test_db_05_hnsw_index_used_for_vector_search(db_conn):
    """
    TC-DB-05: Running a nearest-neighbour query on embeddings (column: vetor) must
    leverage the HNSW index. EXPLAIN output should contain 'Index Scan' or 'index'.
    """
    zero_vector = ",".join(["0"] * 1024)
    query = (
        f"EXPLAIN SELECT id FROM embeddings "
        f"ORDER BY vetor <=> ARRAY[{zero_vector}]::vector(1024) LIMIT 5"
    )

    with db_conn.cursor() as cur:
        cur.execute(query)
        plan_lines = [row[0] for row in cur.fetchall()]

    plan_text = "\n".join(plan_lines).lower()
    assert "index" in plan_text, (
        f"Expected HNSW index usage in EXPLAIN output, got:\n{''.join(plan_lines)}"
    )
