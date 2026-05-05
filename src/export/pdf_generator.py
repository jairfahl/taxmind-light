"""
ESP-17 — Geração server-side de PDFs via WeasyPrint + Jinja2.

Funções públicas:
  generate_pdf(source_type, data, classe, tenant_info) -> bytes
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

try:
    from weasyprint import HTML  # type: ignore[import]
except ImportError:  # pragma: no cover — system deps ausentes no CI
    HTML = None  # type: ignore[assignment,misc]

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)

CLASSE_CONFIG: dict[str, dict[str, Any]] = {
    "alerta":                  {"label": "Alerta",                  "watermark": "ALERTA",      "legalhold": False},
    "nota_trabalho":           {"label": "Nota de Trabalho",        "watermark": "NOTA",        "legalhold": False},
    "recomendacao_formal":     {"label": "Recomendação Formal",     "watermark": "RECOMENDAÇÃO","legalhold": True},
    "dossie_decisao":          {"label": "Dossiê de Decisão",       "watermark": "DOSSIÊ",      "legalhold": True},
    "material_compartilhavel": {"label": "Material Compartilhável", "watermark": "COMPARTILHAR","legalhold": True},
}

STEP_LABELS = {
    1: "Qualificação da Situação",
    2: "Mapeamento Normativo",
    3: "Análise de Materialidade",
    4: "Avaliação de Risco",
    5: "Recomendação Estratégica",
    6: "Dossiê de Decisão",
}

PLANO_LABELS = {
    "pme":      "PME",
    "avancado": "Avançado",
    "trial":    "Trial",
}


_SCORING_ENUM_MAP = {"alto": 80, "medio": 50, "baixo": 20}


def _parse_scoring(value: Any) -> Optional[int]:
    """
    Converte scoring_confianca para inteiro percentual para o template.

    Aceita:
      - string enum: "alto" → 80, "medio" → 50, "baixo" → 20
      - float 0-1: 0.75 → 75
      - int/float > 1: 85 → 85
    Retorna None se não reconhecido.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return _SCORING_ENUM_MAP.get(value.lower())
    try:
        val = float(value)
        return round(val * 100) if val <= 1.0 else int(val)
    except (ValueError, TypeError):
        return None


def _compute_integrity_hash(content_dict: dict) -> str:
    serialized = json.dumps(content_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _render_html(context: dict) -> str:
    template = _jinja_env.get_template("pdf_base.html")
    return template.render(**context)


def _build_context_analysis(data: dict, tenant_info: Optional[dict] = None) -> dict:
    """Monta contexto para exportação de uma análise livre (/v1/analyze)."""
    classe = data.get("classe", "nota_trabalho")
    cfg = CLASSE_CONFIG.get(classe, CLASSE_CONFIG["nota_trabalho"])

    gov_scoring = _parse_scoring(data.get("scoring_confianca"))

    stakeholder_views = []
    for sv in (data.get("saidas_stakeholders") or []):
        stakeholder_views.append({
            "stakeholder": f"{sv.get('emoji', '')} {sv.get('label', sv.get('stakeholder_id', ''))}".strip(),
            "resumo": sv.get("resumo", ""),
        })

    return {
        "source_type": "analysis",
        "titulo": data.get("titulo") or "Análise Tributária",
        "classe_label": cfg["label"],
        "watermark_text": cfg["watermark"],
        "legalhold": cfg["legalhold"],
        "is_dossie": False,
        "data_geracao": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "case_titulo": data.get("case_titulo"),
        "tenant_nome": (tenant_info or {}).get("nome", ""),
        "tenant_cnpj": (tenant_info or {}).get("cnpj"),
        "plano_label": PLANO_LABELS.get((tenant_info or {}).get("plano", ""), None),
        "materialidade": data.get("materialidade"),
        "conteudo_principal": data.get("resposta", ""),
        "passos": None,
        "gov_grau": data.get("grau_consolidacao"),
        "gov_forca": data.get("forca_corrente_contraria"),
        "gov_risco": data.get("risco_adocao"),
        "gov_scoring": gov_scoring,
        "stakeholder_views": stakeholder_views,
        "disclaimer": data.get("disclaimer") or (
            "Esta análise é gerada por inteligência artificial com base nas normas da Reforma "
            "Tributária brasileira (EC 132/2023, LC 214/2025). Não substitui parecer jurídico "
            "ou consultoria especializada. Verifique a vigência das normas antes de tomar decisões."
        ),
        "integrity_hash": None,
    }


def _build_context_dossie(output: dict, case: Optional[dict] = None, tenant_info: Optional[dict] = None) -> dict:
    """Monta contexto para exportação de um dossiê/output do protocolo."""
    classe = output.get("classe", "dossie_decisao")
    cfg = CLASSE_CONFIG.get(classe, CLASSE_CONFIG["dossie_decisao"])

    conteudo = output.get("conteudo") or {}
    is_dossie = classe == "dossie_decisao"

    # Passos P1→P6 a partir do conteúdo estruturado
    passos = []
    if is_dossie and isinstance(conteudo, dict):
        # Formato primário: chaves p1..p6 ou passo_1..passo_6
        for num in range(1, 7):
            chave = f"p{num}"
            texto = conteudo.get(chave) or conteudo.get(f"passo_{num}")
            if texto:
                passos.append({
                    "num": num,
                    "label": STEP_LABELS.get(num, f"Passo {num}"),
                    "texto": texto,
                })

        # Fallback: formato flat gerado por engine.gerar_dossie
        # (chaves: premissas, periodo_fiscal, hipotese_gestor, recomendacao, decisao_final, decisor)
        if not passos:
            def _lista(v):
                if isinstance(v, list):
                    return " | ".join(str(i) for i in v if i)
                return str(v) if v else ""

            _flat = [
                (1, " | ".join(filter(None, [
                    conteudo.get("titulo_caso", ""),
                    _lista(conteudo.get("premissas", [])),
                    f"Período: {conteudo['periodo_fiscal']}" if conteudo.get("periodo_fiscal") else "",
                ]))),
                (4, conteudo.get("hipotese_gestor", "")),
                (5, " | ".join(filter(None, [
                    conteudo.get("recomendacao", ""),
                    conteudo.get("decisao_final", ""),
                    f"Decisor: {conteudo['decisor']}" if conteudo.get("decisor") else "",
                ]))),
            ]
            for num, texto in _flat:
                if texto and texto.strip():
                    passos.append({
                        "num": num,
                        "label": STEP_LABELS.get(num, f"Passo {num}"),
                        "texto": texto,
                    })

    # Conteúdo textual para não-dossiês
    conteudo_principal = ""
    if not is_dossie:
        if isinstance(conteudo, str):
            conteudo_principal = conteudo
        elif isinstance(conteudo, dict):
            conteudo_principal = "\n\n".join(
                str(v) for v in conteudo.values() if isinstance(v, str) and v
            )

    stakeholder_views = []
    for sv in (output.get("stakeholder_views") or []):
        stakeholder_views.append({
            "stakeholder": sv.get("stakeholder", ""),
            "resumo": sv.get("resumo", ""),
        })

    # Hash de integridade apenas para dossiês com Legal Hold
    integrity_hash = None
    if cfg["legalhold"] and isinstance(conteudo, dict):
        integrity_hash = _compute_integrity_hash(conteudo)

    gov_scoring = _parse_scoring(output.get("scoring_confianca"))

    return {
        "source_type": "dossie",
        "titulo": output.get("titulo") or cfg["label"],
        "classe_label": cfg["label"],
        "watermark_text": cfg["watermark"],
        "legalhold": cfg["legalhold"],
        "is_dossie": is_dossie,
        "data_geracao": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        "case_titulo": (case or {}).get("titulo"),
        "tenant_nome": (tenant_info or {}).get("nome", ""),
        "tenant_cnpj": (tenant_info or {}).get("cnpj"),
        "plano_label": PLANO_LABELS.get((tenant_info or {}).get("plano", ""), None),
        "materialidade": output.get("materialidade"),
        "conteudo_principal": conteudo_principal,
        "passos": passos or None,
        "gov_grau": output.get("grau_consolidacao"),
        "gov_forca": output.get("forca_corrente_contraria"),
        "gov_risco": output.get("risco_adocao"),
        "gov_scoring": gov_scoring,
        "stakeholder_views": stakeholder_views,
        "disclaimer": output.get("disclaimer"),
        "integrity_hash": integrity_hash,
    }


def generate_pdf(
    source_type: str,
    data: dict,
    classe: Optional[str] = None,
    tenant_info: Optional[dict] = None,
) -> bytes:
    """
    Gera PDF em memória e retorna os bytes.

    source_type: "analysis" | "dossie"
    data: dicionário com campos da análise ou do output
    classe: sobrescreve data["classe"] se fornecido
    tenant_info: {"nome": str, "cnpj": str|None, "plano": str|None}
    """
    if classe:
        data = {**data, "classe": classe}

    if source_type == "analysis":
        context = _build_context_analysis(data, tenant_info)
    else:
        context = _build_context_dossie(data, tenant_info=tenant_info)

    html_content = _render_html(context)

    if HTML is None:  # pragma: no cover
        raise RuntimeError("WeasyPrint não instalado. Instale as system deps (libpango, libcairo).")
    pdf_bytes: bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes


def pdf_filename(source_type: str, classe: Optional[str] = None) -> str:
    """Retorna o nome de arquivo conforme ESP-17 §Nomenclatura."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    if source_type == "analysis":
        return f"orbis_orientacao_{date_str}.pdf"
    class_map = {
        "dossie_decisao": "dossie",
        "recomendacao_formal": "recomendacao",
        "material_compartilhavel": "material",
        "alerta": "alerta",
        "nota_trabalho": "nota",
    }
    suffix = class_map.get(classe or "", "documento")
    return f"orbis_{suffix}_{date_str}.pdf"
