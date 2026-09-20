"""
Schemas do módulo `calcular_valor_causa`.
"""
from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class IndiceCorrecao(str, Enum):
    INPC = "INPC"
    IPCA = "IPCA"
    IGP_M = "IGP-M"
    SELIC = "SELIC"
    TR = "TR"
    NENHUM = "nenhum"


class ComponenteValorCausa(BaseModel):
    descricao: str
    valor_original: float
    data_base: Optional[date] = None
    indice_correcao: IndiceCorrecao = IndiceCorrecao.NENHUM
    juros_mensais_pct: Optional[float] = None
    multa_pct: Optional[float] = None


class DanosMoraisInput(BaseModel):
    pedido: bool = False
    valor_sugerido: Optional[float] = None


class CalcularValorCausaRequest(BaseModel):
    componentes: List[ComponenteValorCausa]
    danos_morais: Optional[DanosMoraisInput] = None
    data_calculo: Optional[date] = None  # se omitido, usa a data de hoje


class ItemMemoriaCalculo(BaseModel):
    descricao: str
    valor_original: float
    meses_decorridos: Optional[float] = None
    juros_aplicados: float = 0.0
    multa_aplicada: float = 0.0
    correcao_monetaria_pendente: bool = False
    indice_correcao: Optional[IndiceCorrecao] = None
    valor_atualizado: float  # não inclui correção monetária quando pendente


class RespostaValorCausa(BaseModel):
    itens: List[ItemMemoriaCalculo] = Field(default_factory=list)
    subtotal_componentes: float
    danos_morais_incluidos: float = 0.0
    valor_da_causa: float
    ha_correcao_monetaria_pendente: bool
    data_calculo: date
    observacoes: str = (
        "Correção monetária por índice (INPC/IPCA/IGP-M/SELIC/TR) NÃO é "
        "calculada automaticamente aqui — exige a tabela oficial vigente do "
        "índice no período, que este sistema não possui. Aplique-a "
        "externamente (ex.: calculadora do tribunal ou do CJF) e some ao "
        "valor indicado quando 'correcao_monetaria_pendente' for true. "
        "Juros e multa, quando informados, já estão somados nesta memória. "
        "O valor de danos morais aqui é apenas o valor SUGERIDO informado "
        "por quem pediu o cálculo, não uma estimativa baseada em "
        "jurisprudência."
    )
