"""
src/cognitive/metodos.py — Biblioteca de métodos de análise tributária.

Define os 10 métodos disponíveis para o gestor selecionar no Passo 1,
e a tabela de sugestão automática por nível de criticidade.
"""

from __future__ import annotations

METODOS_ANALISE: dict[str, dict] = {
    "cenarios": {
        "nome": "Análise de Cenários",
        "descricao": "Avalia múltiplos futuros possíveis (otimista, neutro, pessimista) e seus impactos tributários.",
        "quando_usar": "Incerteza regulatória alta ou transições legislativas em andamento.",
    },
    "simulacao_carga": {
        "nome": "Simulação de Carga Tributária",
        "descricao": "Calcula o impacto financeiro real de diferentes regimes e alíquotas sobre o faturamento.",
        "quando_usar": "Decisão de regime tributário ou mudança de enquadramento.",
    },
    "matriz_risco": {
        "nome": "Matriz de Risco",
        "descricao": "Mapeia probabilidade × impacto de cada risco tributário identificado.",
        "quando_usar": "Múltiplos riscos concorrentes que precisam ser priorizados.",
    },
    "arvore_decisao": {
        "nome": "Árvore de Decisão",
        "descricao": "Estrutura as opções e consequências legais em forma de árvore, facilitando escolha sequencial.",
        "quando_usar": "Casos com ramificações de decisão dependentes entre si.",
    },
    "benchmarking": {
        "nome": "Benchmarking Setorial",
        "descricao": "Compara práticas e alíquotas efetivas do setor para identificar desvios ou oportunidades.",
        "quando_usar": "Avaliar se a carga tributária da empresa está alinhada ao setor.",
    },
    "analise_custo_beneficio": {
        "nome": "Análise Custo-Benefício",
        "descricao": "Pesa os custos de conformidade, consultoria e eventual litígio contra os benefícios esperados.",
        "quando_usar": "Decisão sobre impugnar auto de infração ou recorrer administrativamente.",
    },
    "teoria_jogos": {
        "nome": "Teoria dos Jogos",
        "descricao": "Analisa a interação estratégica entre contribuinte, fisco e terceiros (fornecedores, clientes).",
        "quando_usar": "Negociações fiscais complexas ou riscos de litígio com contrapartes.",
    },
    "analise_precedentes": {
        "nome": "Análise de Precedentes",
        "descricao": "Revisa jurisprudência administrativa (CARF) e judicial para identificar tendências de julgamento.",
        "quando_usar": "Questão interpretativa com histórico de disputas jurídicas.",
    },
    "due_diligence_fiscal": {
        "nome": "Due Diligence Fiscal",
        "descricao": "Revisão sistemática de obrigações, passivos e contingências tributárias do período.",
        "quando_usar": "M&A, reestruturação societária ou levantamento de passivos históricos.",
    },
    "planejamento_tributario": {
        "nome": "Planejamento Tributário",
        "descricao": "Identifica oportunidades lícitas de redução de carga via reorganização de estrutura ou timing.",
        "quando_usar": "Início de exercício fiscal, mudança de porte ou nova atividade econômica.",
    },
}

SUGESTAO_POR_CRITICIDADE: dict[str, list[str]] = {
    "extrema": ["cenarios", "simulacao_carga", "teoria_jogos", "matriz_risco"],
    "alta": ["cenarios", "analise_precedentes", "matriz_risco"],
    "media": ["analise_custo_beneficio", "analise_precedentes"],
    "baixa": ["benchmarking", "planejamento_tributario"],
}

MAX_METODOS = 4


def sugerir_metodos(criticidade: str) -> list[str]:
    """Retorna lista de métodos sugeridos para o nível de criticidade."""
    return SUGESTAO_POR_CRITICIDADE.get(criticidade.lower(), SUGESTAO_POR_CRITICIDADE["media"])


def formatar_metodos_para_prompt(metodos_ids: list[str] | None) -> str:
    """
    Converte lista de IDs de métodos em texto estruturado para injeção no prompt do LLM.

    Retorna string vazia se lista for vazia.
    """
    if not metodos_ids:  # handles None, [], falsy
        return ""
    linhas = ["MÉTODOS DE ANÁLISE SELECIONADOS PELO GESTOR:"]
    for mid in metodos_ids:
        m = METODOS_ANALISE.get(mid)
        if m:
            linhas.append(f"• {m['nome']}: {m['descricao']}")
    linhas.append(
        "\nAplique obrigatoriamente os métodos acima na sua análise, "
        "dedicando uma seção ou parágrafo a cada um."
    )
    return "\n".join(linhas)
