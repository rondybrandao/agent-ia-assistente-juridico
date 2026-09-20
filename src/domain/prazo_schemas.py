"""
Schemas do módulo `calcular_prazos`.
"""
from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RegimePrazo(str, Enum):
    CPC = "cpc"
    JEC = "jec"
    CLT = "clt"
    JEF = "jef"


class CalcularPrazoRequest(BaseModel):
    data_intimacao: date
    dias: int
    regime: RegimePrazo
    comarca: Optional[str] = None
    prazo_em_dobro: bool = False


class RespostaPrazo(BaseModel):
    data_intimacao: date
    dias_solicitados: int
    dias_efetivos: int  # já considerando a dobra, se houver
    regime: RegimePrazo
    fundamento_regime: str
    data_inicio_contagem: date
    data_vencimento: date
    dias_nao_uteis_no_periodo: List[date] = Field(default_factory=list)
    alerta_recesso_forense: bool
    observacoes: str = (
        "Cálculo baseado em feriados nacionais, no feriado estadual do "
        "Amazonas (5/9) e nos feriados municipais de Manaus (24/10 e 8/12), "
        "além do recesso forense (20/12 a 20/1). Feriados municipais de "
        "outras comarcas do Amazonas NÃO estão mapeados — confirme "
        "localmente se a comarca não for Manaus. Este cálculo não considera "
        "prorrogações, suspensões pontuais ou peculiaridades do caso "
        "concreto; sempre confira no sistema do tribunal antes do vencimento."
    )
