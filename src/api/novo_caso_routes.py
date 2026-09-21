"""
Rotas HTTP do chat de registro de novos casos — usado pela tela inicial do
Angular, para casos que não vieram do WhatsApp/triagem.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..domain.schemas import SessaoConversa
from ..services.novo_caso_service import novo_caso_service

router = APIRouter(prefix="/api/novo-caso", tags=["novo-caso"])


class NovoCasoMensagemIn(BaseModel):
    case_id: Optional[str] = None
    mensagem: str


class NovoCasoMensagemOut(BaseModel):
    case_id: str
    resposta: str
    sessao: SessaoConversa


@router.post("/mensagem", response_model=NovoCasoMensagemOut)
def enviar_mensagem(corpo: NovoCasoMensagemIn) -> NovoCasoMensagemOut:
    """
    Envia uma mensagem no chat de novo caso. Se `case_id` não for
    informado, cria um caso novo e retorna o ID gerado — o frontend deve
    guardar esse ID e reenviá-lo nas mensagens seguintes da mesma conversa.
    """
    try:
        resposta, sessao = novo_caso_service.processar_mensagem(corpo.case_id, corpo.mensagem)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return NovoCasoMensagemOut(case_id=sessao.telefone, resposta=resposta, sessao=sessao)
