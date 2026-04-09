"""
monitor/sources.py — Scrapers para fontes oficiais de legislacao tributaria.

Cada fonte tem um checker que retorna lista de documentos encontrados.
Erros sao capturados silenciosamente — nunca interrompem o sistema.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Tribus-AI-Monitor/1.0 (legislacao tributaria; contato@empresa.com)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

TIMEOUT = 15  # segundos


@dataclass
class DocumentoDetectado:
    titulo: str
    url: Optional[str]
    data_publicacao: Optional[str]
    resumo: Optional[str]
    fonte_tipo: str


def _fetch(url: str) -> Optional[str]:
    """Faz GET com tratamento de erro robusto."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("Falha ao acessar %s: %s", url, e)
        return None


def _check_dou(url: str) -> list[DocumentoDetectado]:
    """Busca publicacoes recentes no Diario Oficial da Uniao."""
    html = _fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    docs: list[DocumentoDetectado] = []

    # Estrutura do DOU: resultados em divs com classe 'resultado'
    for item in soup.select(".resultado, .resultados-item, .card-item, article"):
        titulo_el = item.select_one("h5, h4, h3, .title, a.title")
        if not titulo_el:
            continue

        titulo = titulo_el.get_text(strip=True)
        # Filtrar por termos relevantes da reforma tributaria
        termos = ["IBS", "CBS", "reforma tributária", "reforma tributaria",
                  "LC 214", "LC 227", "EC 132", "split payment", "CGIBS",
                  "imposto seletivo", "lei complementar"]
        if not any(t.lower() in titulo.lower() for t in termos):
            continue

        link = titulo_el.get("href") or ""
        if link and not link.startswith("http"):
            link = f"https://www.in.gov.br{link}"

        data_el = item.select_one(".date, .data, time")
        data = data_el.get_text(strip=True) if data_el else None

        resumo_el = item.select_one("p, .description, .resumo")
        resumo = resumo_el.get_text(strip=True)[:300] if resumo_el else None

        docs.append(DocumentoDetectado(
            titulo=titulo[:500],
            url=link or None,
            data_publicacao=data,
            resumo=resumo,
            fonte_tipo="dou",
        ))

    logger.info("DOU: %d documentos relevantes encontrados", len(docs))
    return docs


def _check_planalto(url: str) -> list[DocumentoDetectado]:
    """Busca leis complementares recentes no Planalto."""
    html = _fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    docs: list[DocumentoDetectado] = []

    for link_el in soup.select("a[href]"):
        texto = link_el.get_text(strip=True)
        href = link_el.get("href", "")

        # Filtrar por LCs recentes (2024+)
        if not re.search(r"lcp\d+", href, re.IGNORECASE):
            continue

        if href and not href.startswith("http"):
            href = f"https://www.planalto.gov.br{href}"

        docs.append(DocumentoDetectado(
            titulo=texto[:500] if texto else href.split("/")[-1],
            url=href,
            data_publicacao=None,
            resumo=None,
            fonte_tipo="planalto",
        ))

    logger.info("Planalto: %d leis complementares encontradas", len(docs))
    return docs


def _check_cgibs(url: str) -> list[DocumentoDetectado]:
    """Busca orientacoes e notas no portal do CGIBS."""
    html = _fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    docs: list[DocumentoDetectado] = []

    for item in soup.select("a[href]"):
        texto = item.get_text(strip=True)
        href = item.get("href", "")

        # Filtrar por documentos relevantes
        termos = ["orientação", "orientacao", "nota", "guia", "instrução",
                  "instrucao", "IBS", "CBS", "reforma"]
        if not any(t.lower() in texto.lower() for t in termos):
            continue
        if len(texto) < 10:
            continue

        if href and not href.startswith("http"):
            href = f"https://www.gov.br{href}"

        docs.append(DocumentoDetectado(
            titulo=texto[:500],
            url=href or None,
            data_publicacao=None,
            resumo=None,
            fonte_tipo="cgibs",
        ))

    logger.info("CGIBS: %d documentos encontrados", len(docs))
    return docs


def _check_nfe(url: str) -> list[DocumentoDetectado]:
    """Busca notas tecnicas no portal NF-e."""
    html = _fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    docs: list[DocumentoDetectado] = []

    for item in soup.select("a[href]"):
        texto = item.get_text(strip=True)
        href = item.get("href", "")

        # Filtrar por NTs relevantes
        if not re.search(r"(nota\s+t[eé]cnica|NT[_ ]|RTC)", texto, re.IGNORECASE):
            continue
        if len(texto) < 10:
            continue

        if href and not href.startswith("http"):
            if "nfe.fazenda" in url:
                href = f"https://www.nfe.fazenda.gov.br/portal/{href}"

        docs.append(DocumentoDetectado(
            titulo=texto[:500],
            url=href or None,
            data_publicacao=None,
            resumo=None,
            fonte_tipo="nfe",
        ))

    logger.info("NF-e: %d notas tecnicas encontradas", len(docs))
    return docs


def _check_rfb(url: str) -> list[DocumentoDetectado]:
    """Busca legislacao na Receita Federal."""
    html = _fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    docs: list[DocumentoDetectado] = []

    for item in soup.select("a[href]"):
        texto = item.get_text(strip=True)
        href = item.get("href", "")

        termos = ["instrução normativa", "instrucao normativa", "IN RFB",
                  "reforma tributária", "reforma tributaria", "IBS", "CBS"]
        if not any(t.lower() in texto.lower() for t in termos):
            continue
        if len(texto) < 10:
            continue

        if href and not href.startswith("http"):
            href = f"https://www.gov.br{href}"

        docs.append(DocumentoDetectado(
            titulo=texto[:500],
            url=href or None,
            data_publicacao=None,
            resumo=None,
            fonte_tipo="rfb",
        ))

    logger.info("RFB: %d documentos encontrados", len(docs))
    return docs


def _check_sijut2(url: str) -> list[DocumentoDetectado]:
    """
    Busca atos normativos recentes no SIJUT2 (Receita Federal).
    Usa parâmetros GET para busca por termos da Reforma Tributária.
    URL base: https://normas.receita.fazenda.gov.br/sijut2consulta/consulta.action
    """
    termos_busca = "IBS CBS reforma tributária imposto seletivo split payment"
    url_busca = (
        f"{url}?visao=anonima"
        f"&txtPesquisa={termos_busca.replace(' ', '+')}"
        f"&chkTipoDocumento=on"
        f"&hdnTipoDocumento="
    )

    html = _fetch(url_busca)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    docs: list[DocumentoDetectado] = []

    # SIJUT2 retorna resultados em tabela ou lista de links de atos
    for item in soup.select("a[href]"):
        texto = item.get_text(strip=True)
        href = item.get("href", "")

        if len(texto) < 10:
            continue

        # Filtrar por atos normativos relevantes
        termos = [
            "instrução normativa", "IN RFB", "portaria", "resolução",
            "IBS", "CBS", "reforma tributária", "imposto seletivo",
            "split payment", "LC 214", "LC 227", "EC 132",
        ]
        if not any(t.lower() in texto.lower() for t in termos):
            continue

        if href and not href.startswith("http"):
            base = "https://normas.receita.fazenda.gov.br"
            href = f"{base}{href}" if href.startswith("/") else f"{base}/sijut2consulta/{href}"

        docs.append(DocumentoDetectado(
            titulo=texto[:500],
            url=href or None,
            data_publicacao=None,
            resumo=None,
            fonte_tipo="sijut2",
        ))

    logger.info("SIJUT2: %d documentos encontrados", len(docs))
    return docs


# Mapa de checkers por tipo de fonte
CHECKERS = {
    "dou": _check_dou,
    "planalto": _check_planalto,
    "cgibs": _check_cgibs,
    "nfe": _check_nfe,
    "rfb": _check_rfb,
    "sijut2": _check_sijut2,
}
