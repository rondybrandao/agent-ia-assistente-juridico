"""
Schemas do módulo `verificar_citacao`.

Camada: domain. Separado dos schemas de estratégia porque é um sub-domínio
próprio, consumido pelo VerificacaoCitacaoService.
"""
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TipoCitacao(str, Enum):
    LEI = "lei"
    ARTIGO = "artigo"
    SUMULA = "sumula"
    ACORDAO = "acordao"
    TEMA = "tema"


class StatusVerificacao(str, Enum):
    CONFIRMADA = "confirmada"  # existe, número/órgão corretos, vigente, trecho confere (se houver)
    DIVERGENTE = "divergente"  # existe algo parecido, mas número/órgão/trecho não batem exatamente
    DESATUALIZADA = "desatualizada"  # existiu, mas foi cancelada/superada/revista
    NAO_ENCONTRADA = "nao_encontrada"  # nenhuma evidência de que existe
    INCONCLUSIVA = "inconclusiva"  # busca não trouxe evidência suficiente pra decidir


class CitacaoEntrada(BaseModel):
    tipo: TipoCitacao
    referencia: str  # ex.: "REsp 1.234.567/SP", "Súmula 297 STJ"
    trecho_citado: Optional[str] = None


class ResultadoVerificacaoCitacao(BaseModel):
    tipo: TipoCitacao
    referencia: str
    status: StatusVerificacao
    existe: bool
    trecho_confere: Optional[bool] = None  # null se não foi fornecido trecho pra conferir
    vigente: Optional[bool] = None  # null quando não é aplicável (ex.: lei sem indício de revogação)
    fonte_url: Optional[str] = None
    observacao: str  # explicação curta da decisão, sempre baseada nas evidências buscadas


class RespostaVerificacaoCitacoes(BaseModel):
    resultados: List[ResultadoVerificacaoCitacao] = Field(default_factory=list)
