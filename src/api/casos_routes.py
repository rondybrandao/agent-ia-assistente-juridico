"""
Rotas HTTP REST usadas pelo frontend Angular do advogado.

Camada: api — só fala HTTP e delega a lógica real para os services e
repositories. Não confundir com api/webhook_routes.py, que é o canal do
WhatsApp; este router é o canal da página web.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..domain.schemas import SessaoConversa
from ..repositories.session_repository import sessao_repository
from ..services.pesquisa_juridica_service import pesquisa_juridica_service

router = APIRouter(prefix="/api/casos", tags=["casos"])


class CasoResumoOut(BaseModel):
    telefone: str
    nome: Optional[str]
    area_direito: str
    urgencia: str
    status_caso: str
    resumo_caso: Optional[str]


class PerguntaIn(BaseModel):
    mensagem: str


class RespostaOut(BaseModel):
    resposta: str


def _to_resumo_out(sessao: SessaoConversa) -> CasoResumoOut:
    r = sessao.resumo_atual
    return CasoResumoOut(
        telefone=sessao.telefone,
        nome=sessao.contato.nome,
        area_direito=r.area_direito.value,
        urgencia=r.urgencia.value,
        status_caso=sessao.status_caso.value,
        resumo_caso=r.resumo_caso,
    )


@router.get("", response_model=List[CasoResumoOut])
def listar_casos() -> List[CasoResumoOut]:
    """Lista os casos que já têm algum resumo de triagem (para a sidebar)."""
    sessoes = sessao_repository.listar_todas()
    return [_to_resumo_out(s) for s in sessoes if s.resumo_atual.resumo_caso]


@router.get("/{telefone}", response_model=SessaoConversa)
def obter_caso(telefone: str) -> SessaoConversa:
    """Retorna o caso completo: resumo, conversa original, anotações e
    histórico do chat de pesquisa jurídica."""
    sessao = sessao_repository.carregar(telefone)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return sessao


@router.post("/{telefone}/pesquisa", response_model=RespostaOut)
async def perguntar_pesquisa(telefone: str, corpo: PerguntaIn) -> RespostaOut:
    """Envia uma pergunta do advogado ao chat de pesquisa jurídica do caso."""
    sessao = sessao_repository.carregar(telefone)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    resposta = await pesquisa_juridica_service.perguntar(sessao, corpo.mensagem)
    sessao_repository.salvar(sessao)
    return RespostaOut(resposta=resposta)
