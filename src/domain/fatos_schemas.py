"""
Schemas do módulo `extrair_fatos`.

Transforma o relato livre do usuário (e, futuramente, o texto extraído de
documentos por ler_documentos — ainda não implementado) numa linha do
tempo estruturada. Nunca infere dado que não foi dito explicitamente.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class EventoLinhaDoTempo(BaseModel):
    data: Optional[str] = None  # ISO (AAAA-MM-DD) quando precisa; null se não informado
    data_aproximada_texto: Optional[str] = None  # ex.: "início de 2024", quando não há data exata
    descricao: str
    fonte: str  # "relato" ou o id de um documento (documentos_ids)


class ParteIdentificada(BaseModel):
    papel: str  # ex.: "autor", "réu", "testemunha"
    nome: Optional[str] = None
    qualificacao: Optional[str] = None  # CPF, endereço etc., só se mencionado


class ValorMencionado(BaseModel):
    descricao: str
    valor: Optional[float] = None
    moeda: str = "BRL"
    data_referencia: Optional[str] = None


class PontoControvertido(BaseModel):
    descricao: str
    motivo: str  # por que é controvertido / o que ainda precisa ser esclarecido


class LacunaFato(BaseModel):
    dado_faltante: str
    impacto: str


class ExtrairFatosRequest(BaseModel):
    relato: str
    documentos_ids: List[str] = Field(default_factory=list)


class RespostaExtracaoFatos(BaseModel):
    resumo_narrativo: str
    linha_do_tempo: List[EventoLinhaDoTempo] = Field(default_factory=list)
    partes: List[ParteIdentificada] = Field(default_factory=list)
    valores_mencionados: List[ValorMencionado] = Field(default_factory=list)
    pontos_controvertidos: List[PontoControvertido] = Field(default_factory=list)
    lacunas: List[LacunaFato] = Field(default_factory=list)
    aviso: str = (
        "Extração baseada apenas no que foi relatado — não constitui "
        "verificação factual nem prova de nenhuma das informações."
    )
