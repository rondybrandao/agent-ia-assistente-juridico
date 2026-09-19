"""
Schemas do módulo `gerar_estrategias`, espelhando o JSON definido em
prompt_estrategias.md. Mantido separado de domain/schemas.py porque é um
sub-domínio próprio (estratégia jurídica), usado apenas pelo
EstrategiaService.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProbabilidadeQualitativa(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"


class AlertaCritico(BaseModel):
    tipo: str  # prescricao | decadencia | competencia | requerimento_administrativo | litispendencia | outro
    descricao: str
    acao_recomendada: str


class Lacuna(BaseModel):
    dado_faltante: str
    impacto: str


class Fundamento(BaseModel):
    texto: str
    fonte: str  # referência verificada OU "fundamento a verificar: ..."


class TutelaUrgencia(BaseModel):
    cabivel: bool
    justificativa: str


class EstimativaCusto(BaseModel):
    custas: str
    honorarios_sucumbencia: str
    observacao: str


class EstimativaPrazo(BaseModel):
    faixa: str
    base: str  # "Datajud" ou "estimativa qualitativa"


class Estrategia(BaseModel):
    id: str
    nome: str
    via: str
    rito: str
    eixos_de_diferenca: List[str]
    resumo: str
    fundamentos: List[Fundamento] = Field(default_factory=list)
    pedidos_principais: List[str] = Field(default_factory=list)
    tutela_urgencia: TutelaUrgencia
    pontos_fortes: List[str] = Field(default_factory=list)
    riscos: List[str] = Field(default_factory=list)
    provas_necessarias: List[str] = Field(default_factory=list)
    provas_ja_disponiveis: List[str] = Field(default_factory=list)
    estimativa_custo: EstimativaCusto
    estimativa_prazo: EstimativaPrazo
    probabilidade_qualitativa: ProbabilidadeQualitativa
    justificativa_probabilidade: str
    quando_escolher: str


class Comparativo(BaseModel):
    criterios: List[str]
    matriz: Dict[str, Dict[str, str]]


class Recomendacao(BaseModel):
    estrategia_id: str
    motivo: str
    condicoes_para_mudar: str


class RespostaEstrategias(BaseModel):
    alertas_criticos: List[AlertaCritico] = Field(default_factory=list)
    lacunas: List[Lacuna] = Field(default_factory=list)
    estrategias: List[Estrategia]
    comparativo: Optional[Comparativo] = None
    recomendacao: Optional[Recomendacao] = None
    aviso: str
