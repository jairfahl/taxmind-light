"""
src/tasks/scheduler.py — Jobs diários de retenção de usuários (anti-churn).

Jobs:
  check_trial_expiring   — 09h00 UTC: e-mail D-2 e D-1 do trial
  check_inactive_tenants — 09h30 UTC: e-mail "sentimos sua falta" (14 dias sem análise)

Inicializado no lifespan da FastAPI (main.py).
Rastreamento via colunas trial_d3_email_sent_at, trial_d1_email_sent_at,
inactivity_email_sent_at na tabela tenants (migration 127).
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

# IDs únicos por job — evitam colisão com outros advisory locks na app
_LOCK_TRIAL_EXPIRING    = 900001
_LOCK_INACTIVE_TENANTS  = 900002


@contextmanager
def _pg_advisory_lock(lock_id: int):
    """
    Context manager que adquire um advisory lock de sessão no PostgreSQL.
    Se outro worker já segura o lock, retorna sem executar (yield False).
    Garante unicidade do job em ambientes multi-worker (uvicorn --workers N).
    """
    from src.db.pool import get_conn, put_conn

    conn = get_conn()
    acquired = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            acquired = cur.fetchone()[0]
        yield acquired
    finally:
        if acquired:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
            except Exception:
                pass
        put_conn(conn)


def check_trial_expiring() -> None:
    """
    Verifica trials próximos do vencimento e envia e-mails D-2 e D-1.
    Cada e-mail é enviado apenas uma vez (rastreado pelas colunas *_sent_at).
    O trial NÃO é prorrogado — e-mails são apenas avisos.
    Advisory lock garante execução única mesmo com múltiplos workers.
    """
    with _pg_advisory_lock(_LOCK_TRIAL_EXPIRING) as acquired:
        if not acquired:
            logger.info("[scheduler] check_trial_expiring ignorado — outro worker já executa")
            return
        _run_check_trial_expiring()


def _run_check_trial_expiring() -> None:
    from src.db.pool import get_conn, put_conn
    from src.email_service import enviar_email_trial_expirando

    logger.info("[scheduler] check_trial_expiring iniciado")
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, u.email, u.nome, t.trial_ends_at,
                       t.trial_d3_email_sent_at, t.trial_d1_email_sent_at
                FROM tenants t
                JOIN users u ON u.tenant_id = t.id AND u.perfil = 'ADMIN'
                WHERE t.subscription_status = 'trial'
                  AND t.trial_ends_at IS NOT NULL
                """
            )
            rows = cur.fetchall()

        agora = datetime.now(timezone.utc)

        for tenant_id, email, nome, trial_ends_at, d3_sent, d1_sent in rows:
            if isinstance(trial_ends_at, str):
                from datetime import datetime as _dt
                trial_ends_at = _dt.fromisoformat(trial_ends_at)
            if trial_ends_at.tzinfo is None:
                trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)

            dias = (trial_ends_at.date() - agora.date()).days

            if dias == 2 and d3_sent is None:
                enviar_email_trial_expirando(email, nome, 2)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE tenants SET trial_d3_email_sent_at = NOW() WHERE id = %s",
                        (tenant_id,),
                    )
                conn.commit()
                logger.info("[scheduler] E-mail D-2 enviado para tenant %s (%s)", tenant_id, email)

            elif dias == 1 and d1_sent is None:
                enviar_email_trial_expirando(email, nome, 1)
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE tenants SET trial_d1_email_sent_at = NOW() WHERE id = %s",
                        (tenant_id,),
                    )
                conn.commit()
                logger.info("[scheduler] E-mail D-1 enviado para tenant %s (%s)", tenant_id, email)

    except Exception as exc:
        logger.error("[scheduler] Erro em check_trial_expiring: %s", exc, exc_info=True)
    finally:
        if conn:
            put_conn(conn)


def check_inactive_tenants() -> None:
    """
    Identifica assinantes ativos sem nenhuma análise nos últimos 14 dias
    e envia e-mail de reengajamento (1 envio por tenant — rastreado por
    inactivity_email_sent_at; reset quando houver nova análise).
    Advisory lock garante execução única mesmo com múltiplos workers.
    """
    with _pg_advisory_lock(_LOCK_INACTIVE_TENANTS) as acquired:
        if not acquired:
            logger.info("[scheduler] check_inactive_tenants ignorado — outro worker já executa")
            return
        _run_check_inactive_tenants()


def _run_check_inactive_tenants() -> None:
    from src.db.pool import get_conn, put_conn
    from src.email_service import enviar_email_inatividade

    logger.info("[scheduler] check_inactive_tenants iniciado")
    conn = None
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, u.email, u.nome
                FROM tenants t
                JOIN users u ON u.tenant_id = t.id AND u.perfil = 'ADMIN'
                WHERE t.subscription_status = 'active'
                  AND t.inactivity_email_sent_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM ai_interactions ai
                    JOIN users u2 ON u2.id = ai.user_id
                    WHERE u2.tenant_id = t.id
                      AND ai.created_at > NOW() - INTERVAL '14 days'
                  )
                """
            )
            rows = cur.fetchall()

        for tenant_id, email, nome in rows:
            enviar_email_inatividade(email, nome)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tenants SET inactivity_email_sent_at = NOW() WHERE id = %s",
                    (tenant_id,),
                )
            conn.commit()
            logger.info("[scheduler] E-mail inatividade enviado para tenant %s (%s)", tenant_id, email)

    except Exception as exc:
        logger.error("[scheduler] Erro em check_inactive_tenants: %s", exc, exc_info=True)
    finally:
        if conn:
            put_conn(conn)


def create_scheduler() -> BackgroundScheduler:
    """
    Cria e configura o BackgroundScheduler com os jobs de retenção.
    Chamado no lifespan da FastAPI; retorna instância pronta para .start().
    """
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(check_trial_expiring,   "cron", hour=9,  minute=0,  id="trial_expiring")
    scheduler.add_job(check_inactive_tenants, "cron", hour=9,  minute=30, id="inactive_tenants")
    logger.info("[scheduler] Jobs registrados: trial_expiring (09h00 UTC), inactive_tenants (09h30 UTC)")
    return scheduler
