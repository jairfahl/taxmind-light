"""
outputs/engine.py — OutputEngine: geração e gestão das 5 classes de output.

Classes:
  C1 — Alerta            (P2 ou P6, sistema automático)
  C2 — Nota de Trabalho  (P3, analista)
  C3 — Recomendação      (P3, motor cognitivo)
  C4 — Dossiê de Decisão (P5, compilação automática)
  C5 — Material Compartilhável (derivado de C3/C4 aprovado)
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import psycopg2
from dotenv import load_dotenv

from src.db.pool import get_conn, put_conn

from src.cognitive.engine import AnaliseResult
from src.outputs.materialidade import MaterialidadeCalculator
from src.outputs.stakeholders import StakeholderDecomposer, StakeholderTipo, StakeholderView

load_dotenv()
logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1.0.0-sprint4"
BASE_VERSION = "LC214_2025+EC132_2023+LC227_2026"

DISCLAIMER_PADRAO = (
    "Este output foi gerado com suporte de inteligência artificial (Orbis.tax). "
    "Não substitui parecer jurídico ou consultoria tributária especializada. "
    "Fundamentação legal: verificada na base de conhecimento na data de geração. "
    "Validade sujeita a alterações legislativas posteriores."
)


class OutputClass(str, Enum):
    ALERTA = "alerta"
    NOTA_TRABALHO = "nota_trabalho"
    RECOMENDACAO_FORMAL = "recomendacao_formal"
    DOSSIE_DECISAO = "dossie_decisao"
    MATERIAL_COMPARTILHAVEL = "material_compartilhavel"


class OutputStatus(str, Enum):
    RASCUNHO = "rascunho"
    GERADO = "gerado"
    APROVADO = "aprovado"
    PUBLICADO = "publicado"
    REVOGADO = "revogado"


class OutputError(ValueError):
    """Erro de validação do OutputEngine."""


@dataclass
class OutputResult:
    id: str
    case_id: str
    passo_origem: int
    classe: OutputClass
    status: OutputStatus
    titulo: str
    conteudo: dict
    materialidade: int
    disclaimer: str
    versao_prompt: Optional[str]
    versao_base: Optional[str]
    stakeholder_views: list[StakeholderView] = field(default_factory=list)
    created_at: str = ""


def _get_conn() -> psycopg2.extensions.connection:
    return get_conn()


def _assert_disclaimer(disclaimer: str) -> None:
    """Disclaimer NUNCA pode ser nulo ou vazio — falha hard."""
    if not disclaimer or not disclaimer.strip():
        raise OutputError("disclaimer não pode ser nulo ou vazio")


def _insert_output(
    conn,
    case_id: str,
    passo_origem: int,
    classe: OutputClass,
    titulo: str,
    conteudo: dict,
    materialidade: int,
    disclaimer: str,
    versao_prompt: Optional[str],
    versao_base: Optional[str],
) -> str:
    _assert_disclaimer(disclaimer)
    imutavel = classe in (OutputClass.DOSSIE_DECISAO, OutputClass.MATERIAL_COMPARTILHAVEL)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO outputs
            (case_id, passo_origem, classe, status, titulo, conteudo,
             materialidade, disclaimer, versao_prompt, versao_base, imutavel)
        VALUES (%s, %s, %s::output_class, 'gerado', %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (case_id, passo_origem, classe.value, titulo,
         json.dumps(conteudo, ensure_ascii=False),
         materialidade, disclaimer, versao_prompt, versao_base, imutavel),
    )
    output_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    logger.info("Output criado: id=%s case_id=%s classe=%s", output_id, case_id, classe.value)
    return output_id


def _load_output(conn, output_id: str) -> OutputResult:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, case_id, passo_origem, classe, status, titulo, conteudo,
               materialidade, disclaimer, versao_prompt, versao_base, created_at
        FROM outputs WHERE id = %s
        """,
        (output_id,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        raise OutputError(f"Output {output_id} não encontrado")

    # Carregar views de stakeholders
    cur.execute(
        "SELECT id, stakeholder, resumo, campos_visiveis FROM output_stakeholders WHERE output_id = %s",
        (output_id,),
    )
    views = []
    for r in cur.fetchall():
        views.append(StakeholderView(
            output_id=output_id,
            stakeholder=StakeholderTipo(r[1]),
            resumo=r[2],
            campos_visiveis=list(r[3]) if r[3] else [],
            db_id=r[0],
        ))
    cur.close()

    conteudo = row[6] if isinstance(row[6], dict) else json.loads(row[6])
    return OutputResult(
        id=row[0], case_id=row[1], passo_origem=row[2],
        classe=OutputClass(row[3]), status=OutputStatus(row[4]),
        titulo=row[5], conteudo=conteudo,
        materialidade=row[7] or 3, disclaimer=row[8],
        versao_prompt=row[9], versao_base=row[10],
        stakeholder_views=views, created_at=str(row[11]),
    )


class OutputEngine:

    def __init__(self):
        self._mat_calc = MaterialidadeCalculator()
        self._stk_decomp = StakeholderDecomposer()

    # ------------------------------------------------------------------
    # C1 — Alerta
    # ------------------------------------------------------------------
    def gerar_alerta(
        self,
        case_id: str,
        passo: int,
        titulo: str,
        contexto: str,
        materialidade: int,
        stakeholders: Optional[list[StakeholderTipo]] = None,
    ) -> OutputResult:
        """Gera Alerta (C1) a partir de P2 ou P6."""
        if passo not in (2, 6):
            raise OutputError("Alerta (C1) só pode ser gerado em P2 ou P6")
        if not 1 <= materialidade <= 5:
            raise OutputError("materialidade deve estar entre 1 e 5")
        _assert_disclaimer(DISCLAIMER_PADRAO)

        conteudo = {"contexto": contexto, "titulo": titulo}
        conn = _get_conn()
        try:
            output_id = _insert_output(
                conn, case_id, passo, OutputClass.ALERTA,
                titulo, conteudo, materialidade, DISCLAIMER_PADRAO,
                None, None,
            )
            if stakeholders:
                self._stk_decomp.decompor(output_id, stakeholders, conteudo, conn)
            return _load_output(conn, output_id)
        finally:
            put_conn(conn)

    # ------------------------------------------------------------------
    # C2 — Nota de Trabalho
    # ------------------------------------------------------------------
    def gerar_nota_trabalho(
        self,
        case_id: str,
        analise_result: AnaliseResult,
        stakeholders: Optional[list[StakeholderTipo]] = None,
    ) -> OutputResult:
        """Gera Nota de Trabalho (C2) a partir de AnaliseResult do P3."""
        if analise_result is None:
            raise OutputError("analise_result é obrigatório para Nota de Trabalho (C2)")
        if not analise_result.query:
            raise OutputError("analise_result inválido: campo query ausente")

        _assert_disclaimer(DISCLAIMER_PADRAO)

        titulo = f"Nota de Trabalho — {analise_result.query[:80]}"
        conteudo = {
            "query": analise_result.query,
            "resposta": analise_result.resposta,
            "fundamento_legal": analise_result.fundamento_legal,
            "grau_consolidacao": analise_result.grau_consolidacao,
            "scoring_confianca": analise_result.scoring_confianca,
            "anti_alucinacao": {
                "m1_existencia": analise_result.anti_alucinacao.m1_existencia,
                "m2_validade": analise_result.anti_alucinacao.m2_validade,
                "m3_pertinencia": analise_result.anti_alucinacao.m3_pertinencia,
                "m4_consistencia": analise_result.anti_alucinacao.m4_consistencia,
                "bloqueado": analise_result.anti_alucinacao.bloqueado,
            },
            "versao_prompt": analise_result.prompt_version,
            "versao_base": BASE_VERSION,
        }
        contexto_mat = {
            "query": analise_result.query,
            "grau_consolidacao": analise_result.grau_consolidacao,
            "scoring_confianca": analise_result.scoring_confianca,
        }
        materialidade = self._mat_calc.calcular(contexto_mat)

        conn = _get_conn()
        try:
            output_id = _insert_output(
                conn, case_id, 3, OutputClass.NOTA_TRABALHO,
                titulo, conteudo, materialidade, DISCLAIMER_PADRAO,
                analise_result.prompt_version, BASE_VERSION,
            )
            if stakeholders:
                self._stk_decomp.decompor(output_id, stakeholders, conteudo, conn)
            return _load_output(conn, output_id)
        finally:
            put_conn(conn)

    # ------------------------------------------------------------------
    # C3 — Recomendação Formal
    # ------------------------------------------------------------------
    def gerar_recomendacao_formal(
        self,
        case_id: str,
        analise_result: AnaliseResult,
        stakeholders: Optional[list[StakeholderTipo]] = None,
    ) -> OutputResult:
        """Gera Recomendação Formal (C3) a partir de AnaliseResult do P3."""
        if analise_result is None:
            raise OutputError("analise_result é obrigatório para Recomendação Formal (C3)")
        if not analise_result.query:
            raise OutputError("analise_result inválido: campo query ausente")
        if analise_result.anti_alucinacao.bloqueado:
            raise OutputError("Recomendação bloqueada: anti-alucinação ativado na análise")

        _assert_disclaimer(DISCLAIMER_PADRAO)

        titulo = f"Recomendação Formal — {analise_result.query[:80]}"
        conteudo = {
            "recomendacao_principal": analise_result.resposta,
            "fundamento_legal": analise_result.fundamento_legal,
            "grau_consolidacao": analise_result.grau_consolidacao,
            "contra_tese": analise_result.contra_tese,
            "scoring_confianca": analise_result.scoring_confianca,
            "versao_prompt": analise_result.prompt_version,
            "versao_base": BASE_VERSION,
            "chunks_usados": len(analise_result.chunks) if analise_result.chunks else 0,
        }
        contexto_mat = {
            "query": analise_result.query,
            "fundamento_legal": analise_result.fundamento_legal,
            "grau_consolidacao": analise_result.grau_consolidacao,
        }
        materialidade = self._mat_calc.calcular(contexto_mat)

        conn = _get_conn()
        try:
            output_id = _insert_output(
                conn, case_id, 3, OutputClass.RECOMENDACAO_FORMAL,
                titulo, conteudo, materialidade, DISCLAIMER_PADRAO,
                analise_result.prompt_version, BASE_VERSION,
            )
            if stakeholders:
                self._stk_decomp.decompor(output_id, stakeholders, conteudo, conn)
            return _load_output(conn, output_id)
        finally:
            put_conn(conn)

    # ------------------------------------------------------------------
    # C4 — Dossiê de Decisão
    # ------------------------------------------------------------------
    def gerar_dossie(
        self,
        case_id: str,
        stakeholders: Optional[list[StakeholderTipo]] = None,
    ) -> OutputResult:
        """
        Gera Dossiê (C4) compilando P1+P4+P5.
        Requer P5 concluído.
        """
        conn = _get_conn()
        try:
            cur = conn.cursor()

            # Verificar P5 concluído
            cur.execute(
                "SELECT concluido, dados FROM case_steps WHERE case_id=%s AND passo=5",
                (case_id,),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise OutputError("Dossiê (C4) requer P5 (Decidir) concluído")

            # Coletar dados dos passos relevantes
            passos_dados = {}
            for p in (1, 2, 3, 4, 5):
                cur.execute(
                    "SELECT dados FROM case_steps WHERE case_id=%s AND passo=%s",
                    (case_id, p),
                )
                r = cur.fetchone()
                if r:
                    dados = r[0] if isinstance(r[0], dict) else json.loads(r[0])
                    passos_dados[p] = dados

            cur.execute("SELECT titulo FROM cases WHERE id=%s", (case_id,))
            titulo_caso = cur.fetchone()[0]
            cur.close()

            titulo = f"Dossiê de Decisão — {titulo_caso[:80]}"
            conteudo = {
                "titulo_caso": titulo_caso,
                "premissas": passos_dados.get(1, {}).get("premissas", []),
                "periodo_fiscal": passos_dados.get(1, {}).get("periodo_fiscal", ""),
                "hipotese_gestor": passos_dados.get(4, {}).get("hipotese_gestor", ""),
                "recomendacao": passos_dados.get(5, {}).get("recomendacao", ""),
                "decisao_final": passos_dados.get(5, {}).get("decisao_final", ""),
                "decisor": passos_dados.get(5, {}).get("decisor", ""),
                "versao_prompt": PROMPT_VERSION,
                "versao_base": BASE_VERSION,
            }
            contexto_mat = {
                "titulo_caso": titulo_caso,
                "decisao_final": conteudo["decisao_final"],
            }
            materialidade = self._mat_calc.calcular(contexto_mat)

            output_id = _insert_output(
                conn, case_id, 5, OutputClass.DOSSIE_DECISAO,
                titulo, conteudo, materialidade, DISCLAIMER_PADRAO,
                PROMPT_VERSION, BASE_VERSION,
            )
            if stakeholders:
                self._stk_decomp.decompor(output_id, stakeholders, conteudo, conn)
            return _load_output(conn, output_id)
        finally:
            put_conn(conn)

    # ------------------------------------------------------------------
    # C5 — Material Compartilhável
    # ------------------------------------------------------------------
    def gerar_material_compartilhavel(
        self,
        output_id: str,
        stakeholders: list[StakeholderTipo],
    ) -> OutputResult:
        """
        Gera Material Compartilhável (C5) a partir de C3 ou C4 aprovado.
        Requer output_id com status='aprovado' e classe in (C3, C4).
        """
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT case_id, classe, status, conteudo FROM outputs WHERE id=%s",
                (output_id,),
            )
            row = cur.fetchone()
            if not row:
                raise OutputError(f"Output {output_id} não encontrado")
            case_id, classe_str, status_str, conteudo_raw = row
            cur.close()

            classe = OutputClass(classe_str)
            status = OutputStatus(status_str)

            if classe not in (OutputClass.RECOMENDACAO_FORMAL, OutputClass.DOSSIE_DECISAO):
                raise OutputError("Material Compartilhável (C5) exige C3 ou C4 como base")
            if status != OutputStatus.APROVADO:
                raise OutputError(
                    f"Material Compartilhável (C5) exige output base com status='aprovado' "
                    f"(atual: '{status.value}')"
                )

            conteudo_base = conteudo_raw if isinstance(conteudo_raw, dict) else json.loads(conteudo_raw)
            titulo = f"Material Compartilhável — derivado de output #{output_id}"
            # Conteúdo já filtrado para compartilhamento seguro
            conteudo = {
                "titulo": titulo,
                "recomendacao_principal": conteudo_base.get("recomendacao_principal")
                    or conteudo_base.get("recomendacao", ""),
                "fundamento_legal": conteudo_base.get("fundamento_legal", []),
                "disclaimer": DISCLAIMER_PADRAO,
                "output_base_id": output_id,
            }
            materialidade = self._mat_calc.calcular({"titulo": titulo})

            new_output_id = _insert_output(
                conn, case_id, 5, OutputClass.MATERIAL_COMPARTILHAVEL,
                titulo, conteudo, materialidade, DISCLAIMER_PADRAO,
                PROMPT_VERSION, BASE_VERSION,
            )
            if stakeholders:
                self._stk_decomp.decompor(new_output_id, stakeholders, conteudo, conn)
            return _load_output(conn, new_output_id)
        finally:
            put_conn(conn)

    # ------------------------------------------------------------------
    # Aprovar
    # ------------------------------------------------------------------
    def aprovar(
        self,
        output_id: str,
        aprovado_por: str,
        observacao: Optional[str] = None,
    ) -> OutputResult:
        """
        Aprova um output (C3 ou C5 exigem aprovação antes de 'publicado').
        Transições válidas: gerado → aprovado.
        """
        if not aprovado_por or not aprovado_por.strip():
            raise OutputError("aprovado_por é obrigatório")

        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT status FROM outputs WHERE id=%s", (output_id,))
            row = cur.fetchone()
            if not row:
                raise OutputError(f"Output {output_id} não encontrado")
            status_atual = OutputStatus(row[0])
            if status_atual not in (OutputStatus.RASCUNHO, OutputStatus.GERADO):
                raise OutputError(
                    f"Output {output_id} não pode ser aprovado (status atual: '{status_atual.value}')"
                )

            cur.execute(
                "UPDATE outputs SET status='aprovado', updated_at=NOW() WHERE id=%s",
                (output_id,),
            )
            cur.execute(
                "INSERT INTO output_aprovacoes (output_id, aprovado_por, observacao) VALUES (%s, %s, %s)",
                (output_id, aprovado_por.strip(), observacao),
            )
            conn.commit()
            cur.close()
            logger.info("Output aprovado: id=%s por=%s", output_id, aprovado_por)
            return _load_output(conn, output_id)
        finally:
            put_conn(conn)

    # ------------------------------------------------------------------
    # Listar por caso
    # ------------------------------------------------------------------
    def listar_por_caso(self, case_id: str) -> list[OutputResult]:
        """Lista todos os outputs de um caso, ordenados por materialidade DESC."""
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM outputs WHERE case_id=%s ORDER BY materialidade DESC NULLS LAST, created_at DESC",
                (case_id,),
            )
            ids = [r[0] for r in cur.fetchall()]
            cur.close()
            return [_load_output(conn, oid) for oid in ids]
        finally:
            put_conn(conn)
