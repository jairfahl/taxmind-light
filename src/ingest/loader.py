"""
loader.py — extrai texto dos PDFs das normas tributárias.
Lê de PDF_SOURCE_DIR (definido em .env). Nunca copia PDFs.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PDF_SOURCE_DIR = os.getenv("PDF_SOURCE_DIR", "")

# Mapeamento fixo: nome do arquivo → metadados da norma
NORMA_MAP: dict[str, dict] = {
    "EC132_2023.pdf": {
        "codigo": "EC132_2023",
        "nome": "Emenda Constitucional nº 132, de 20 de dezembro de 2023",
        "tipo": "EC",
        "numero": "132",
        "ano": 2023,
    },
    "LC214_2025.pdf": {
        "codigo": "LC214_2025",
        "nome": "Lei Complementar nº 214, de 16 de janeiro de 2025",
        "tipo": "LC",
        "numero": "214",
        "ano": 2025,
    },
    "LC227_2026.pdf": {
        "codigo": "LC227_2026",
        "nome": "Lei Complementar nº 227, de 2026",
        "tipo": "LC",
        "numero": "227",
        "ano": 2026,
    },
}


@dataclass
class DocumentoNorma:
    codigo: str
    nome: str
    tipo: str
    numero: str
    ano: int
    arquivo: str
    texto: str


def extrair_texto_pdf(caminho: Path) -> str:
    """Extrai texto de um PDF usando pdfplumber."""
    paginas: list[str] = []
    with pdfplumber.open(caminho) as pdf:
        for i, pagina in enumerate(pdf.pages):
            texto = pagina.extract_text()
            if texto:
                paginas.append(texto)
            else:
                logger.debug("Página %d sem texto extraível em %s", i + 1, caminho.name)
    return "\n".join(paginas)


def carregar_normas() -> list[DocumentoNorma]:
    """
    Carrega todos os PDFs mapeados de PDF_SOURCE_DIR.
    Retorna lista de DocumentoNorma com texto completo.
    """
    if not PDF_SOURCE_DIR:
        raise EnvironmentError("PDF_SOURCE_DIR não definido no .env")

    source_dir = Path(PDF_SOURCE_DIR)
    if not source_dir.exists():
        raise FileNotFoundError(f"Diretório de PDFs não encontrado: {source_dir}")

    documentos: list[DocumentoNorma] = []
    for filename, meta in NORMA_MAP.items():
        caminho = source_dir / filename
        if not caminho.exists():
            logger.warning("PDF não encontrado, pulando: %s", caminho)
            continue

        logger.info("Carregando PDF: %s", filename)
        texto = extrair_texto_pdf(caminho)
        doc = DocumentoNorma(
            codigo=meta["codigo"],
            nome=meta["nome"],
            tipo=meta["tipo"],
            numero=meta["numero"],
            ano=meta["ano"],
            arquivo=str(caminho),
            texto=texto,
        )
        documentos.append(doc)
        logger.info("  → %d caracteres extraídos de %s", len(texto), filename)

    return documentos
