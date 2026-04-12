"""
src/startup_validation.py — Validação de variáveis de ambiente no startup.

Falha explicitamente com mensagem clara antes de qualquer módulo de negócio.
Evita o padrão silencioso: ValueError em import → API não sobe → nginx 502.

Chamado em src/api/main.py como primeira linha executável.
"""
import os
import sys


def validate_env() -> None:
    """
    Valida variáveis de ambiente críticas.
    Imprime todos os erros encontrados e chama sys.exit(1) se houver algum.
    """
    errors: list[str] = []

    # ── Variáveis obrigatórias ────────────────────────────────────────────────
    required = [
        "DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "VOYAGE_API_KEY",
        "JWT_SECRET",
        "API_INTERNAL_KEY",
    ]
    for var in required:
        if not os.getenv(var):
            errors.append(f"[MISSING] {var} não definida ou vazia")

    # ── Variáveis com valores enum ────────────────────────────────────────────
    # LOCKFILE_MODE: causa ValueError silencioso ao importar engine.py
    lockfile_mode = os.getenv("LOCKFILE_MODE", "WARN")
    if lockfile_mode not in ("WARN", "BLOCK"):
        errors.append(
            f"[INVALID] LOCKFILE_MODE='{lockfile_mode}' — valores válidos: WARN, BLOCK  "
            f"(ENFORCE não é válido)"
        )

    # LOG_LEVEL: usado pelo logging.basicConfig
    log_level = os.getenv("LOG_LEVEL", "INFO")
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        errors.append(
            f"[INVALID] LOG_LEVEL='{log_level}' — valores válidos: "
            f"DEBUG, INFO, WARNING, ERROR, CRITICAL"
        )

    # ── Variáveis numéricas ───────────────────────────────────────────────────
    numeric_vars = {
        "TOP_K": (1, 50),
        "RERANK_TOP_N": (1, 100),
        "CHUNK_SIZE": (64, 4096),
        "CHUNK_OVERLAP": (0, 512),
    }
    for var, (min_val, max_val) in numeric_vars.items():
        raw = os.getenv(var)
        if raw is not None:
            try:
                val = int(raw)
                if not (min_val <= val <= max_val):
                    errors.append(
                        f"[INVALID] {var}={raw} — deve estar entre {min_val} e {max_val}"
                    )
            except ValueError:
                errors.append(f"[INVALID] {var}='{raw}' — deve ser um inteiro")

    api_credit = os.getenv("API_CREDIT_LIMIT_USD")
    if api_credit is not None:
        try:
            float(api_credit)
        except ValueError:
            errors.append(
                f"[INVALID] API_CREDIT_LIMIT_USD='{api_credit}' — deve ser um número decimal"
            )

    # ── Resultado ─────────────────────────────────────────────────────────────
    if errors:
        print("\n" + "=" * 60, file=sys.stderr)
        print("TRIBUS-AI — ERRO DE CONFIGURAÇÃO NO STARTUP", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("Corrija as variáveis acima e reinicie a API.", file=sys.stderr)
        print("", file=sys.stderr)
        sys.exit(1)

    print("[startup] Variáveis de ambiente validadas com sucesso.")
