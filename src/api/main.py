"""
api/main.py — FastAPI application entry point.

Monta o app e inclui todos os routers modulares.
A lógica de negócio vive em src/api/routers/*.py
"""

# === VALIDAÇÃO DE STARTUP — deve ser a primeira coisa a executar ===
from dotenv import load_dotenv as _load_dotenv_early
_load_dotenv_early()
from src.startup_validation import validate_env as _validate_env
_validate_env()
# ====================================================================

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.limiter import limiter
from src.db.pool import get_conn, put_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    from src.tasks.scheduler import create_scheduler
    from src.db.pool import close_pool
    scheduler = create_scheduler()
    scheduler.start()
    yield
    scheduler.shutdown()
    close_pool()


_is_dev = os.getenv("ENV") == "dev"
app = FastAPI(
    title="Tribus-AI API",
    description="Motor cognitivo para análise da Reforma Tributária brasileira",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/v1/docs" if _is_dev else None,
    redoc_url="/v1/redoc" if _is_dev else None,
    openapi_url="/v1/openapi.json" if _is_dev else None,
)

_prod_origins = ["https://orbis.tax", "https://www.orbis.tax"]
_dev_origins  = ["http://localhost:8521", "http://localhost:3000", "http://localhost:3001", "http://localhost:3002"]
_cors_origins = _prod_origins + (_dev_origins if _is_dev else [])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Api-Key"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Health check ---

@app.get("/v1/health")
def health():
    """Status do sistema com contagens e lista de normas disponíveis."""
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM chunks")
        chunks_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM embeddings")
        embeddings_total = cur.fetchone()[0]
        cur.execute("SELECT codigo, nome FROM normas WHERE vigente = TRUE ORDER BY ano, codigo")
        normas = [{"codigo": r[0], "nome": r[1]} for r in cur.fetchall()]
        cur.close()
    except Exception:
        raise HTTPException(status_code=500, detail="Serviço temporariamente indisponível.")
    finally:
        if conn:
            put_conn(conn)

    cache_stats = {}
    try:
        from src.resilience.cache import _query_cache
        cache_stats = _query_cache.stats
    except Exception:
        pass

    return {
        "status": "ok",
        "chunks_total": chunks_total,
        "embeddings_total": embeddings_total,
        "normas": normas,
        "cache_stats": cache_stats,
    }


# --- Routers ---

from src.api.routers import (
    admin,
    analyze,
    auth,
    billing,
    cases,
    ingest,
    observability,
    outputs,
    simuladores,
)

app.include_router(auth.router)
app.include_router(analyze.router)
app.include_router(cases.router)
app.include_router(outputs.router)
app.include_router(ingest.router)
app.include_router(observability.router)
app.include_router(billing.router)
app.include_router(admin.router)
app.include_router(simuladores.router)

# Backwards-compat re-exports for tests that import or patch via src.api.main
from src.api.routers.analyze import _analise_to_dict          # noqa: F401, E402
from src.api.routers.auth import get_limite_casos              # noqa: F401, E402
from src.api.helpers import (                                  # noqa: F401, E402
    _get_tenant_info_by_user,
    _verificar_limite_casos,
)
# get_conn/put_conn already imported above — re-used by patcher via src.api.main namespace
