"""
Schemas do módulo `gerar_peticao`.

Camada: domain. `fatos`, `partes`, `competencia` ficam como dict genérico
de propósito: cada template usa um conjunto diferente de campos (autor/réu
num caso de consumo, reclamante/reclamada num trabalhista etc.), então uma
estrutura rígida aqui atrapalharia mais do que ajudaria — a validação de
"quais campos esse template espera" mora no próprio JSON de templates.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CitacaoParaPeca(BaseModel):
    """Uma citação já verificada, pronta para uso na peça (não conter aqui
    é o que impede o agente de inventar fundamento)."""
    tipo: str
    referencia: str
    fonte_url: Optional[str] = None
    trecho_citado: Optional[str] = None


class PeticaoRequest(BaseModel):
    template_id: str
    telefone: Optional[str] = None  # se informado, auto-preenche estrategia_escolhida do caso
    estrategia_escolhida: Dict[str, Any] = Field(default_factory=dict)
    fatos: Dict[str, Any] = Field(default_factory=dict)
    partes: Dict[str, Any] = Field(default_factory=dict)
    competencia: Dict[str, Any] = Field(default_factory=dict)
    valor_causa: float
    citacoes_verificadas: List[CitacaoParaPeca] = Field(default_factory=list)
    pedidos_adicionais: List[str] = Field(default_factory=list)


class Peca(BaseModel):
    """Uma peça gerada e persistida — o que revisar_peticao e
    exportar_documento consultam a partir do peca_id."""
    peca_id: str
    template_id: str
    titulo: str
    peca_texto: str
    campos_pendentes: List[str] = Field(default_factory=list)
    citacoes_utilizadas: List[CitacaoParaPeca] = Field(default_factory=list)
    criada_em: datetime = Field(default_factory=datetime.utcnow)


class PeticaoResponse(BaseModel):
    peca_id: str
    template_id: str
    titulo: str
    peca_texto: str
    campos_pendentes: List[str] = Field(default_factory=list)
    aviso: str = (
        "Este é um RASCUNHO gerado por IA. Precisa de revisão completa e "
        "assinatura de advogado antes de qualquer uso ou protocolo."
    )