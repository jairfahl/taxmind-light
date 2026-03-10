"""
validacao.py — executa as 10 consultas de validação da Sprint 1 e registra em avaliacoes.
Critério: top-3 pertinente ≥ 8/10.
"""

import logging
import os
import time
import psycopg2
from dotenv import load_dotenv
from src.rag.retriever import retrieve

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CONSULTAS = [
    (1,  "Qual o fato gerador do IBS?"),
    (2,  "Quais operações são imunes ao IBS e CBS?"),
    (3,  "Como funciona o split payment?"),
    (4,  "Quais setores têm redução de 60% na alíquota?"),
    (5,  "O que é o CGIBS e quais são suas competências?"),
    (6,  "Qual o prazo de transição para extinção do ICMS?"),
    (7,  "Como é calculada a alíquota de referência do IBS?"),
    (8,  "Quais medicamentos têm alíquota zero?"),
    (9,  "Como funciona o cashback do IBS/CBS?"),
    (10, "Quais são as regras do IBS no Simples Nacional?"),
]

# Avaliação automática de pertinência por palavras-chave esperadas
KEYWORDS = {
    1:  ["fato gerador", "IBS", "CBS", "ocorrido", "fornecimento"],
    2:  ["imun", "IBS", "CBS", "impost", "operaç"],
    3:  ["split payment", "pagamento", "recolhimento", "financeiro"],
    4:  ["60%", "redução", "alíquota", "setor"],
    5:  ["CGIBS", "Comitê Gestor", "competência", "IBS"],
    6:  ["transição", "ICMS", "prazo", "extinção"],
    7:  ["alíquota de referência", "IBS", "calculad", "percentual"],
    8:  ["medicamento", "alíquota zero", "farmacêutico", "zero"],
    9:  ["cashback", "devolução", "benefício", "restituição"],
    10: ["Simples Nacional", "IBS", "optante", "regime"],
}


def avaliar_pertinencia(num: int, resultados) -> bool:
    """Retorna True se ao menos 1 dos top-3 for pertinente (contém keywords esperadas)."""
    kws = [k.lower() for k in KEYWORDS[num]]
    for r in resultados:
        texto = r.texto.lower()
        if sum(1 for k in kws if k in texto) >= 2:
            return True
    return False


def registrar(conn, query: str, resultados, pertinente: bool, nota: int, obs: str):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO avaliacoes (query_texto, top3_pertinente, nota, observacao)
        VALUES (%s, %s, %s, %s)
        """,
        (query, pertinente, nota, obs),
    )
    conn.commit()
    cur.close()


def main():
    url = os.getenv("DATABASE_URL")
    conn = psycopg2.connect(url)

    pertinentes = 0
    print("\n" + "="*80)
    print("TASK-08 — Validação Manual (10 consultas)")
    print("="*80)

    for i, (num, query) in enumerate(CONSULTAS):
        logger.info("Consulta %d/%d: %s", num, len(CONSULTAS), query)
        resultados = retrieve(query, top_k=3)

        pertinente = avaliar_pertinencia(num, resultados)
        nota = 5 if pertinente else 2

        print(f"\n[{num:02d}] {query}")
        print(f"     Pertinente: {'✓' if pertinente else '✗'}  |  Nota: {nota}/5")
        for j, r in enumerate(resultados, 1):
            print(f"     [{j}] score={r.score_final:.3f} | {r.norma_codigo} | {r.artigo} | {r.texto[:120]}")

        obs = f"Auto-avaliado. Keywords encontradas: {pertinente}"
        registrar(conn, query, resultados, pertinente, nota, obs)

        if pertinente:
            pertinentes += 1

        # Rate limit: aguardar entre consultas (exceto a última)
        if i < len(CONSULTAS) - 1:
            time.sleep(25)

    conn.close()

    print("\n" + "="*80)
    print(f"RESULTADO FINAL: {pertinentes}/10 consultas com top-3 pertinente")
    criterio = "✓ APROVADO" if pertinentes >= 8 else "✗ REPROVADO"
    print(f"Critério (≥8/10): {criterio}")
    print("="*80)


if __name__ == "__main__":
    main()
