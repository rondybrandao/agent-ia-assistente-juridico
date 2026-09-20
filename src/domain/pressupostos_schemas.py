"""
Schemas do módulo `checar_pressupostos`.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TipoPressuposto(str, Enum):
    PRESCRICAO = "prescricao"
    DECADENCIA = "decadencia"
    LEGITIMIDADE = "legitimidade"
    INTERESSE_DE_AGIR = "interesse_de_agir"
    REQUERIMENTO_ADMINISTRATIVO_PREVIO = "requerimento_administrativo_previo"
    LITISPENDENCIA_OU_COISA_JULGADA = "litispendencia_ou_coisa_julgada"
    OUTRO = "outro"


class StatusPressuposto(str, Enum):
    OK = "ok"  # sem indício de problema
    RISCO = "risco"  # há indício de problema que precisa de atenção
    LACUNA = "lacuna"  # falta dado para avaliar esse pressuposto


class AvaliacaoPressuposto(BaseModel):
    tipo: TipoPressuposto
    status: StatusPressuposto
    analise: str
    dado_faltante: Optional[str] = None  # preenchido quando status == LACUNA


class CheckPressupostosRequest(BaseModel):
    area: str
    fatos: dict = Field(default_factory=dict)
    data_ultimo_fato: Optional[str] = None  # formato "AAAA-MM-DD"


class RespostaPressupostos(BaseModel):
    avaliacoes: List[AvaliacaoPressuposto] = Field(default_factory=list)
    tem_risco_critico: bool  # true se algum pressuposto está "risco" (não "lacuna")
    aviso: str = (
        "Esta é uma triagem preliminar de pressupostos processuais, não uma "
        "análise jurídica definitiva. Prescrição, decadência e legitimidade "
        "dependem de exame aprofundado pelo advogado responsável."
    )
