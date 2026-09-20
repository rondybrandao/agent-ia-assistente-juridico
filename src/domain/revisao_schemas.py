"""
Schemas do módulo `revisar_peticao`.
"""
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class ChecklistDisponivel(str, Enum):
    CPC_319 = "cpc_319"
    CLT_840 = "clt_840"
    JEC_LEI_9099 = "jec_lei_9099"
    JEF_LEI_10259 = "jef_lei_10259"


class StatusItemChecklist(str, Enum):
    OK = "ok"
    FALTANDO = "faltando"
    ATENCAO = "atencao"  # presente, mas merece olhar humano com cuidado


class ItemRevisao(BaseModel):
    item: str
    status: StatusItemChecklist
    observacao: str


class RespostaRevisao(BaseModel):
    peca_id: str
    checklist_usado: ChecklistDisponivel
    itens: List[ItemRevisao] = Field(default_factory=list)
    tem_pendencia: bool  # true se algum item está "faltando" ou "atencao"
    aviso: str = (
        "Este checklist é um apoio, não substitui a revisão do advogado "
        "responsável. A responsabilidade pela peça é sempre humana."
    )
