"""
validacao_sprint2.py — processa os 3 casos tributários P1→P4 da Sprint 2.
Registra resultados e verifica critérios de aceite.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.cognitive.engine import analisar

logging.basicConfig(level=logging.WARNING)

CASOS = [
    {
        "id": "C1",
        "query": "Empresa do setor de saúde vende planos de saúde. Qual o impacto do IBS com a Reforma Tributária?",
        "criterios": {
            # Art. 138 (redução 60% serviços saúde) OU Arts. 234-238 (regime específico planos saúde)
            "artigo_saude": True,
            "scoring_nao_vermelho": True,
        },
    },
    {
        "id": "C2",
        "query": "Qual o regime de transição do ICMS para o IBS entre 2026 e 2033?",
        "criterios": {
            "menciona_transicao": True,
            "grau_consolidado": True,
        },
    },
    {
        "id": "C3",
        "query": "Como funciona o split payment para e-commerce com plataforma digital intermediária?",
        "criterios": {
            "artigo_split": True,
            "contra_tese": True,
        },
    },
]


def avaliar_caso(caso: dict, resultado) -> tuple[bool, list[str]]:
    ok = True
    notas = []
    crit = caso["criterios"]

    if crit.get("artigo_esperado"):
        art = crit["artigo_esperado"]
        encontrou = any(art in f for f in resultado.fundamento_legal) or \
                    any(art in c.artigo for c in resultado.chunks if c.artigo)
        if encontrou:
            notas.append(f"✓ Art. {art} citado")
        else:
            notas.append(f"✗ Art. {art} NÃO citado (fundamentos: {resultado.fundamento_legal})")
            ok = False

    if crit.get("artigo_saude"):
        # Aceitar Art. 138 (redução serviços saúde) OU Arts. 113/234-238 (planos de saúde)
        artigos_saude = ["138", "234", "235", "236", "237", "238", "113"]
        encontrou = any(
            any(a in f for a in artigos_saude) for f in resultado.fundamento_legal
        ) or any(
            c.artigo and any(a in c.artigo for a in artigos_saude)
            for c in resultado.chunks
        )
        if encontrou:
            notas.append(f"✓ Artigo de saúde citado: {[f for f in resultado.fundamento_legal if any(a in f for a in artigos_saude)]}")
        else:
            notas.append(f"✗ Nenhum artigo de saúde citado (fundamentos: {resultado.fundamento_legal})")
            ok = False

    if crit.get("scoring_nao_vermelho"):
        if resultado.scoring_confianca != "baixo" and not resultado.anti_alucinacao.bloqueado:
            notas.append(f"✓ Scoring: {resultado.scoring_confianca}")
        else:
            notas.append(f"✗ Scoring inadequado: {resultado.scoring_confianca}")
            ok = False

    if crit.get("menciona_transicao"):
        menciona = "transição" in resultado.resposta.lower() or "transition" in resultado.resposta.lower() or \
                   any("385" in f or "233" in f or "132" in f or "2026" in f for f in resultado.fundamento_legal)
        if menciona:
            notas.append("✓ Transição mencionada")
        else:
            notas.append("✗ Transição não mencionada na resposta")
            ok = False

    if crit.get("grau_consolidado"):
        if resultado.grau_consolidacao in ("consolidado", "divergente"):
            notas.append(f"✓ grau_consolidacao: {resultado.grau_consolidacao}")
        else:
            notas.append(f"✗ grau_consolidacao = {resultado.grau_consolidacao} (esperado: consolidado/divergente)")
            ok = False

    if crit.get("artigo_split"):
        artigos_split = any(
            any(x in f for x in ["31", "32", "33", "34", "35"])
            for f in resultado.fundamento_legal
        )
        if artigos_split:
            notas.append("✓ Art. split payment (31-35) citado")
        else:
            notas.append(f"✗ Artigos split payment não citados (fundamentos: {resultado.fundamento_legal})")
            ok = False

    if crit.get("contra_tese"):
        if resultado.contra_tese:
            notas.append(f"✓ Contra-tese gerada: {resultado.contra_tese[:80]}...")
        else:
            notas.append("⚠ Contra-tese não gerada (não-bloqueante)")

    return ok, notas


def main():
    aprovados = 0
    print("\n" + "=" * 80)
    print("TASK-07 — Validação dos 3 Casos Tributários Sprint 2")
    print("=" * 80)

    for caso in CASOS:
        print(f"\n[{caso['id']}] {caso['query']}")
        print("-" * 70)

        resultado = analisar(caso["query"])

        print(f"  Qualidade    : {resultado.qualidade.status.value.upper()}")
        print(f"  Scoring      : {resultado.scoring_confianca}")
        print(f"  Consolidação : {resultado.grau_consolidacao}")
        print(f"  Latência     : {resultado.latencia_ms}ms")
        print(f"  Fundamentos  : {resultado.fundamento_legal}")
        print(f"  Anti-Aluc.   : bloqueado={resultado.anti_alucinacao.bloqueado} flags={resultado.anti_alucinacao.flags}")
        print(f"  Resposta     : {resultado.resposta[:200]}...")

        ok, notas = avaliar_caso(caso, resultado)
        for nota in notas:
            print(f"  {nota}")

        if ok:
            print(f"  → CASO {caso['id']}: ✅ APROVADO")
            aprovados += 1
        else:
            print(f"  → CASO {caso['id']}: ❌ REPROVADO")

    print("\n" + "=" * 80)
    print(f"RESULTADO FINAL: {aprovados}/3 casos aprovados")
    criterio = "✅ APROVADO" if aprovados >= 2 else "❌ REPROVADO"
    print(f"Critério Sprint 2: {criterio}")
    print("=" * 80)


if __name__ == "__main__":
    main()
