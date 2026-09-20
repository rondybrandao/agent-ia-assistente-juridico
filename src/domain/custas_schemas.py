"""
Schemas do módulo `calcular_custas`.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RitoCustas(str, Enum):
    JUIZADO_ESPECIAL = "juizado_especial"
    COMUM = "comum"
    TRABALHISTA = "trabalhista"
    FEDERAL_COMUM = "federal_comum"
    JUIZADO_FEDERAL = "juizado_federal"


class CalcularCustasRequest(BaseModel):
    tribunal: str
    rito: RitoCustas
    valor_causa: float
    renda_mensal_autor: Optional[float] = None
    pede_gratuidade: bool = False


class RespostaCustas(BaseModel):
    calculo_disponivel: bool  # false quando este sistema não tem tabela confiável para o rito/tribunal
    custas_estimadas: Optional[float] = None
    fundamento: str
    elegibilidade_gratuidade: str
    alertas: List[str] = Field(default_factory=list)
    observacoes: str = (
        "Custas de vara comum (estadual) e de vara federal comum dependem "
        "da tabela vigente do tribunal específico, que este sistema não "
        "possui — 'custas_estimadas' fica vazio nesses casos "
        "('calculo_disponivel': false). Mesmo nos ritos calculados "
        "(trabalhista, Juizados), confirme no sistema do tribunal antes do "
        "recolhimento: essas tabelas podem mudar por lei ou portaria. A "
        "Justiça Federal, em especial, tem reforma legislativa em "
        "discussão (PL 429/2024) que pode alterar a lógica de cálculo "
        "atual (Lei 9.289/1996)."
    )
