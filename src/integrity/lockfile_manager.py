"""
integrity/lockfile_manager.py — Prompt Integrity Lockfile (RDM-029).

Valida que os prompts de sistema carregados no boot correspondem exatamente
aos prompts aprovados no último gate de validação.

Mecanismo:
  1. gerar_lockfile() — gera lockfile com hashes SHA-256 dos prompts ativos
  2. verificar_integridade() — compara prompts carregados contra lockfile
  3. Modo BLOCK (prod) ou WARN (staging)
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class LockfileMode(Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"


class LockfileStatus(Enum):
    VALID = "VALID"
    DIVERGED = "DIVERGED"
    NOT_FOUND = "NOT_FOUND"


def calcular_hash(conteudo: str) -> str:
    """Calcula SHA-256 de uma string. Retorna hex digest de 64 chars."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def gerar_lockfile(
    prompts: dict[str, str],
    taxmind_version: str,
    gate_origem: str,
    criado_por: str,
) -> dict:
    """Gera lockfile a partir dos prompts ativos.

    Args:
        prompts: {prompt_name: conteudo_texto}
        taxmind_version: versão do Tribus-AI (ex: "1.5.0")
        gate_origem: identificador do gate (ex: "U2")
        criado_por: identificador do executor

    Returns:
        dict com estrutura completa do lockfile para persistência.
    """
    prompt_hashes = {name: calcular_hash(conteudo) for name, conteudo in prompts.items()}
    lockfile_json = {
        "versao": taxmind_version,
        "gate_origem": gate_origem,
        "criado_em": datetime.now(timezone.utc).isoformat(),
        "criado_por": criado_por,
        "prompts": prompt_hashes,
    }
    lockfile_str = json.dumps(lockfile_json, sort_keys=True)
    lockfile_hash = calcular_hash(lockfile_str)

    return {
        "id": str(uuid.uuid4()),
        "lockfile_hash": lockfile_hash,
        "taxmind_version": taxmind_version,
        "prompt_ids": list(prompts.keys()),
        "lockfile_json": lockfile_json,
        "gate_origem": gate_origem,
        "criado_por": criado_por,
    }


def verificar_integridade(
    prompts_carregados: dict[str, str],
    lockfile_ativo: dict,
    modo: LockfileMode = LockfileMode.BLOCK,
) -> dict:
    """Verifica integridade dos prompts carregados contra o lockfile ativo.

    Args:
        prompts_carregados: {prompt_name: conteudo_texto} carregados no boot.
        lockfile_ativo: lockfile_json do registro ativo no banco.
        modo: BLOCK levanta RuntimeError; WARN loga e continua.

    Returns:
        dict com status (LockfileStatus), divergencias (list), mensagem (str).

    Raises:
        RuntimeError: se modo=BLOCK e divergência detectada.
    """
    hashes_esperados = lockfile_ativo.get("prompts", {})
    divergencias = []

    for prompt_name, conteudo in prompts_carregados.items():
        hash_atual = calcular_hash(conteudo)
        hash_esperado = hashes_esperados.get(prompt_name)

        if hash_esperado is None:
            divergencias.append({
                "prompt_id": prompt_name,
                "hash_esperado": "NAO_CONSTA_NO_LOCKFILE",
                "hash_atual": hash_atual,
                "tipo": "PROMPT_NAO_REGISTRADO",
            })
        elif hash_atual != hash_esperado:
            divergencias.append({
                "prompt_id": prompt_name,
                "hash_esperado": hash_esperado,
                "hash_atual": hash_atual,
                "tipo": "HASH_DIVERGENTE",
            })

    if not divergencias:
        return {
            "status": LockfileStatus.VALID,
            "divergencias": [],
            "mensagem": "Integridade verificada — todos os prompts íntegros.",
        }

    mensagem = (
        f"INTEGRIDADE COMPROMETIDA — {len(divergencias)} divergência(s) detectada(s). "
        f"Modo: {modo.value}."
    )

    if modo == LockfileMode.BLOCK:
        raise RuntimeError(
            mensagem + f"\nDivergências: {json.dumps(divergencias, indent=2, ensure_ascii=False)}"
        )

    # WARN: loga e retorna
    logger.warning("[LOCKFILE WARNING] %s", mensagem)
    for d in divergencias:
        logger.warning("  → %s: %s", d["prompt_id"], d["tipo"])

    return {
        "status": LockfileStatus.DIVERGED,
        "divergencias": divergencias,
        "mensagem": mensagem,
    }


def persistir_lockfile(conn, lockfile: dict) -> None:
    """Persiste lockfile no banco, desativando o anterior.

    Args:
        conn: conexão psycopg2.
        lockfile: dict retornado por gerar_lockfile().
    """
    cur = conn.cursor()
    try:
        # Desativar lockfile anterior
        cur.execute("UPDATE prompt_lockfiles SET ativo = FALSE WHERE ativo = TRUE")

        cur.execute(
            """
            INSERT INTO prompt_lockfiles
                (id, lockfile_hash, taxmind_version, prompt_ids, lockfile_json,
                 gate_origem, criado_por)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                lockfile["id"],
                lockfile["lockfile_hash"],
                lockfile["taxmind_version"],
                lockfile["prompt_ids"],
                json.dumps(lockfile["lockfile_json"], ensure_ascii=False),
                lockfile["gate_origem"],
                lockfile["criado_por"],
            ),
        )
        conn.commit()
        logger.info(
            "[LOCKFILE GERADO] gate=%s version=%s hash=%s",
            lockfile["gate_origem"],
            lockfile["taxmind_version"],
            lockfile["lockfile_hash"][:16],
        )
    finally:
        cur.close()


def carregar_lockfile_ativo(conn) -> Optional[dict]:
    """Retorna o lockfile ativo do banco, ou None se não houver."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, lockfile_hash, taxmind_version, lockfile_json,
                   gate_origem, criado_em
            FROM prompt_lockfiles
            WHERE ativo = TRUE
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": str(row[0]),
            "lockfile_hash": row[1],
            "taxmind_version": row[2],
            "lockfile_json": row[3] if isinstance(row[3], dict) else json.loads(row[3]),
            "gate_origem": row[4],
            "criado_em": row[5],
        }
    finally:
        cur.close()
