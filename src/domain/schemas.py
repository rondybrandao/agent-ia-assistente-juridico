"""
Entidades de domínio da triagem jurídica.

Camada: domain — define o "vocabulário" do negócio (o que é uma sessão, um
resumo de triagem, uma mensagem etc). Não depende de FastAPI, LLM, WhatsApp
ou banco de dados; qualquer uma dessas camadas depende deste módulo, nunca
o contrário.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Urgencia(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"  # ex: prisão em flagrante, prazo processual iminente, risco físico


class AreaDireito(str, Enum):
    TRABALHISTA = "trabalhista"
    CIVEL = "civel"
    FAMILIA = "familia"
    PENAL = "penal"
    CONSUMIDOR = "consumidor"
    TRIBUTARIO = "tributario"
    PREVIDENCIARIO = "previdenciario"
    EMPRESARIAL = "empresarial"
    IMOBILIARIO = "imobiliario"
    OUTRO = "outro"
    INDEFINIDO = "indefinido"


class Mensagem(BaseModel):
    remetente: str  # "usuario" | "assistente"
    texto: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DadosContato(BaseModel):
    nome: Optional[str] = None
    telefone: str
    email: Optional[str] = None


class ResumoTriagem(BaseModel):
    """
    Saída estruturada da triagem — o que efetivamente vai para o advogado.
    Nunca contém opinião jurídica, só fatos coletados na conversa.
    """
    area_direito: AreaDireito = AreaDireito.INDEFINIDO
    subtema: Optional[str] = None
    resumo_caso: Optional[str] = None
    urgencia: Urgencia = Urgencia.BAIXA
    motivo_urgencia: Optional[str] = None
    fatos_relevantes: List[str] = Field(default_factory=list)
    documentos_mencionados: List[str] = Field(default_factory=list)
    perguntas_em_aberto: List[str] = Field(default_factory=list)
    pronto_para_advogado: bool = False


class SessaoConversa(BaseModel):
    telefone: str
    contato: DadosContato
    historico: List[Mensagem] = Field(default_factory=list)
    resumo_atual: ResumoTriagem = Field(default_factory=ResumoTriagem)
    consentimento_lgpd: bool = False
    encerrada: bool = False
    encaminhada_advogado: bool = False
    criada_em: datetime = Field(default_factory=datetime.utcnow)
    atualizada_em: datetime = Field(default_factory=datetime.utcnow)