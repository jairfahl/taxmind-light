"""
src/api/routers/simuladores.py — Endpoints dos simuladores tributários (MP-01..MP-05).

POST /v1/simuladores/carga-rt
POST /v1/simuladores/split-payment
POST /v1/simuladores/creditos-ibs
POST /v1/simuladores/reestruturacao
POST /v1/simuladores/impacto-is
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from src.api.auth_api import verificar_token_api

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Validators ---

_REGIMES_VALIDOS = {"lucro_real", "lucro_presumido", "simples_nacional"}
_TIPOS_OP_VALIDOS = {"misto", "so_mercadorias", "so_servicos"}
_CATEGORIAS_CREDITO_VALIDAS = {
    "insumos_diretos", "servicos_tomados", "ativo_imobilizado",
    "fornecedor_simples", "uso_consumo", "operacoes_imunes_isentas", "exportacoes",
}
_UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}
_TIPOS_UNIDADE_VALIDOS = {"CD", "planta", "filial", "escritorio"}
_PRODUTOS_IS_VALIDOS = {
    "tabaco", "bebidas_alcoolicas", "bebidas_acucaradas",
    "veiculos", "embarcacoes", "minerais", "combustiveis", "apostas_jogos",
}
_ELASTICIDADES_VALIDAS = {"alta", "media", "baixa"}


# --- Schemas ---

class SimCargaRTRequest(BaseModel):
    faturamento_anual: float = Field(..., gt=0)
    regime_tributario: str = Field("lucro_real", description="lucro_real | lucro_presumido | simples_nacional")
    tipo_operacao: str = Field("misto", description="misto | so_mercadorias | so_servicos")
    percentual_exportacao: float = Field(0.0, ge=0.0, le=1.0)
    percentual_credito_novo: float = Field(1.0, ge=0.0, le=1.0)

    @field_validator("regime_tributario")
    @classmethod
    def _val_regime(cls, v: str) -> str:
        if v not in _REGIMES_VALIDOS:
            raise ValueError(
                f"regime_tributario inválido: {v!r}. "
                f"Valores aceitos: {sorted(_REGIMES_VALIDOS)}"
            )
        return v

    @field_validator("tipo_operacao")
    @classmethod
    def _val_tipo_op(cls, v: str) -> str:
        if v not in _TIPOS_OP_VALIDOS:
            raise ValueError(
                f"tipo_operacao inválido: {v!r}. "
                f"Valores aceitos: {sorted(_TIPOS_OP_VALIDOS)}"
            )
        return v


class SimSplitPaymentRequest(BaseModel):
    faturamento_mensal: float = Field(..., gt=0)
    pct_vista: float = Field(0.5, ge=0.0, le=1.0)
    pct_prazo: float = Field(0.5, ge=0.0, le=1.0)
    prazo_medio_dias: int = Field(30, ge=1)
    taxa_captacao_am: float = Field(0.02, ge=0.0)
    pct_inadimplencia: float = Field(0.02, ge=0.0, le=1.0)
    aliquota_cbs: float = Field(0.088, ge=0.0)
    aliquota_ibs: float = Field(0.177, ge=0.0)
    pct_creditos: float = Field(0.60, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _val_soma_pct(self) -> "SimSplitPaymentRequest":
        soma = self.pct_vista + self.pct_prazo
        if abs(soma - 1.0) > 0.001:
            raise ValueError(
                f"pct_vista ({self.pct_vista}) + pct_prazo ({self.pct_prazo}) "
                f"deve somar 1.0 — representam a totalidade do faturamento "
                f"(soma atual: {soma:.4f})"
            )
        return self


class ItemAquisicaoInput(BaseModel):
    categoria: str
    valor_mensal: float = Field(..., gt=0)
    aliquota_cbs: float = 0.088
    aliquota_ibs: float = 0.177

    @field_validator("categoria")
    @classmethod
    def _val_categoria(cls, v: str) -> str:
        if v not in _CATEGORIAS_CREDITO_VALIDAS:
            raise ValueError(
                f"categoria inválida: {v!r}. "
                f"Categorias aceitas (LC 214/2025, arts. 28–55): "
                f"{sorted(_CATEGORIAS_CREDITO_VALIDAS)}"
            )
        return v


class SimCreditosRequest(BaseModel):
    itens: list[ItemAquisicaoInput]


class UnidadeInput(BaseModel):
    uf: str
    tipo: str = Field("filial", description="CD | planta | filial | escritorio")
    custo_fixo_anual: float = Field(..., gt=0)
    faturamento_anual: float = Field(..., gt=0)
    beneficio_icms_justifica: bool = True

    @field_validator("uf")
    @classmethod
    def _val_uf(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _UFS_VALIDAS:
            raise ValueError(
                f"UF inválida: {v!r}. "
                "Use a sigla oficial de um dos 27 estados brasileiros."
            )
        return v

    @field_validator("tipo")
    @classmethod
    def _val_tipo_unidade(cls, v: str) -> str:
        if v not in _TIPOS_UNIDADE_VALIDOS:
            raise ValueError(
                f"tipo de unidade inválido: {v!r}. "
                f"Valores aceitos: {sorted(_TIPOS_UNIDADE_VALIDOS)}"
            )
        return v


class SimReestruturacaoRequest(BaseModel):
    unidades: list[UnidadeInput]
    ano_analise: int = 2026


class SimImpactoISRequest(BaseModel):
    produto: str = Field(
        ...,
        description=(
            "tabaco | bebidas_alcoolicas | bebidas_acucaradas | veiculos | "
            "embarcacoes | minerais | combustiveis | apostas_jogos"
        ),
    )
    preco_venda_atual: float = Field(..., gt=0)
    volume_mensal: int = Field(..., gt=0)
    custo_producao: float = Field(..., gt=0)
    elasticidade: str = Field("media", description="alta | media | baixa")
    aliquota_customizada: Optional[float] = None

    @field_validator("produto")
    @classmethod
    def _val_produto_is(cls, v: str) -> str:
        if v not in _PRODUTOS_IS_VALIDOS:
            raise ValueError(
                f"produto IS inválido: {v!r}. "
                f"Sujeitos ao IS (LC 214/2025, art. 412 + Anexo XVII): "
                f"{sorted(_PRODUTOS_IS_VALIDOS)}"
            )
        return v

    @field_validator("elasticidade")
    @classmethod
    def _val_elasticidade(cls, v: str) -> str:
        if v not in _ELASTICIDADES_VALIDAS:
            raise ValueError(
                f"elasticidade inválida: {v!r}. "
                f"Valores aceitos: {sorted(_ELASTICIDADES_VALIDAS)}"
            )
        return v


# --- Endpoints ---

@router.post("/v1/simuladores/carga-rt", dependencies=[Depends(verificar_token_api)])
def simular_carga_rt(req: SimCargaRTRequest):
    """MP-01 — Simulador Comparativo de Carga RT. Retorna cenários por ano (2024→2033)."""
    try:
        from src.simuladores.carga_rt import CenarioOperacional, simular_multiplos_anos
        cenario = CenarioOperacional(
            faturamento_anual=req.faturamento_anual,
            regime_tributario=req.regime_tributario,
            tipo_operacao=req.tipo_operacao,
            percentual_exportacao=req.percentual_exportacao,
            percentual_credito_novo=req.percentual_credito_novo,
        )
        pares = simular_multiplos_anos(cenario)
        resultado = []
        for r in pares:
            resultado.append({
                "ano": r["ano"],
                "atual": {
                    "carga_liquida":    r["carga_liquida_atual"],
                    "aliquota_efetiva": r["aliquota_efetiva_atual"],
                },
                "novo": {
                    "carga_liquida":    r["carga_liquida_nova"],
                    "aliquota_efetiva": r["aliquota_efetiva_nova"],
                },
            })
        return {"resultados": resultado}
    except Exception as e:
        logger.error("Erro em /v1/simuladores/carga-rt: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


@router.post("/v1/simuladores/split-payment", dependencies=[Depends(verificar_token_api)])
def simular_split(req: SimSplitPaymentRequest):
    """MP-05 — Simulador de Impacto do Split Payment no Caixa."""
    try:
        import dataclasses
        from src.simuladores.split_payment import CenarioSplitPayment, simular_split_payment
        cenario = CenarioSplitPayment(
            faturamento_mensal=req.faturamento_mensal,
            pct_vista=req.pct_vista,
            pct_prazo=req.pct_prazo,
            prazo_medio_dias=req.prazo_medio_dias,
            taxa_captacao_am=req.taxa_captacao_am,
            pct_inadimplencia=req.pct_inadimplencia,
            aliquota_cbs=req.aliquota_cbs,
            aliquota_ibs=req.aliquota_ibs,
            pct_creditos=req.pct_creditos,
        )
        resultado = simular_split_payment(cenario)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/split-payment: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


@router.post("/v1/simuladores/creditos-ibs", dependencies=[Depends(verificar_token_api)])
def simular_creditos(req: SimCreditosRequest):
    """MP-02 — Monitor de Créditos IBS/CBS."""
    try:
        import dataclasses
        from src.simuladores.creditos_ibs_cbs import ItemAquisicao, mapear_creditos
        itens = [ItemAquisicao(**i.model_dump()) for i in req.itens]
        resultado = mapear_creditos(itens)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/creditos-ibs: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


@router.post("/v1/simuladores/reestruturacao", dependencies=[Depends(verificar_token_api)])
def simular_reestruturacao(req: SimReestruturacaoRequest):
    """MP-03 — Simulador de Reestruturação RT."""
    try:
        import dataclasses
        from src.simuladores.reestruturacao_rt import UnidadeOperacional, analisar_reestruturacao
        unidades = [UnidadeOperacional(**u.model_dump()) for u in req.unidades]
        resultado = analisar_reestruturacao(unidades, ano_analise=req.ano_analise)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/reestruturacao: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")


@router.post("/v1/simuladores/impacto-is", dependencies=[Depends(verificar_token_api)])
def simular_impacto_is(req: SimImpactoISRequest):
    """MP-04 — Calculadora de Impacto do Imposto Seletivo."""
    try:
        import dataclasses
        from src.simuladores.impacto_is import CenarioIS, calcular_impacto_is
        cenario = CenarioIS(
            produto=req.produto,
            preco_venda_atual=req.preco_venda_atual,
            volume_mensal=req.volume_mensal,
            custo_producao=req.custo_producao,
            elasticidade=req.elasticidade,
            aliquota_customizada=req.aliquota_customizada,
        )
        resultado = calcular_impacto_is(cenario)
        return dataclasses.asdict(resultado)
    except Exception as e:
        logger.error("Erro em /v1/simuladores/impacto-is: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno. Tente novamente.")
