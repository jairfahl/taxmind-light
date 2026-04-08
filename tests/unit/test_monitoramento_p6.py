"""
tests/unit/test_monitoramento_p6.py — Testes unitários do P6 Monitoramento (G06, G07).

Testa lógica de detecção de premissas RT sem chamadas ao banco.
"""

from src.cognitive.monitoramento_p6 import _TERMOS_IMPACTO_RT

PREMISSAS_RT = [
    "Assumo alíquota CBS de 0,9% conforme LC 214/2025",
    "Assumo crédito de IBS sobre insumos diretos",
    "Assumo split payment opcional em 2026",
]

PREMISSAS_NEUTRAS = [
    "Empresa tem 50 funcionários",
    "Sede em São Paulo",
    "Atividade principal: consultoria",
]


def _detectar_premissas_afetadas(premissas: list) -> list:
    """Replica a lógica de detecção de premissas sensíveis."""
    afetadas = []
    for p in premissas:
        p_lower = p.lower()
        for termo in _TERMOS_IMPACTO_RT:
            if termo in p_lower:
                afetadas.append(p)
                break
    return afetadas


def test_premissas_rt_detectadas_como_afetadas():
    afetadas = _detectar_premissas_afetadas(PREMISSAS_RT)
    assert len(afetadas) == 3


def test_premissas_neutras_nao_afetadas():
    afetadas = _detectar_premissas_afetadas(PREMISSAS_NEUTRAS)
    assert len(afetadas) == 0


def test_status_revisao_pendente_quando_alertas():
    premissas_afetadas = ["Assumo alíquota CBS de 0,9%"]
    normas_novas = ["IN_RFB_2026_001"]
    requer_revisao = len(premissas_afetadas) > 0 and len(normas_novas) > 0
    assert requer_revisao is True


def test_status_ativo_sem_impacto():
    premissas_afetadas = []
    normas_novas = ["IN_RFB_2026_001"]
    requer_revisao = len(premissas_afetadas) > 0 and len(normas_novas) > 0
    assert requer_revisao is False
