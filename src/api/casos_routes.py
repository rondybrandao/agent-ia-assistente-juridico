"""
Rotas HTTP REST usadas pelo frontend Angular do advogado.

Camada: api — só fala HTTP e delega a lógica real para os services e
repositories. Não confundir com api/webhook_routes.py, que é o canal do
WhatsApp; este router é o canal da página web.
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..domain.citacao_schemas import CitacaoEntrada
from ..domain.competencia_schemas import RespostaCompetencia
from ..domain.estrategia_schemas import Estrategia
from ..domain.fatos_schemas import RespostaExtracaoFatos
from ..domain.pressupostos_schemas import RespostaPressupostos
from ..domain.schemas import SessaoConversa
from ..repositories.session_repository import sessao_repository
from ..services.estrategia_service import estrategia_service
from ..services.extracao_fatos_service import extracao_fatos_service
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


class EstrategiasIn(BaseModel):
    objetivo_usuario: Optional[str] = None
    num_estrategias: int = 3
    citacoes_candidatas: List[CitacaoEntrada] = []
    buscar_jurisprudencia_automaticamente: bool = False
    buscar_legislacao_automaticamente: bool = False
    competencia: Optional[RespostaCompetencia] = None
    pressupostos: Optional[RespostaPressupostos] = None
    checar_pressupostos_automaticamente: bool = False


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


@router.post("/{telefone}/estrategias")
async def gerar_estrategias(telefone: str, corpo: EstrategiasIn):
    """Gera de 2 a 4 caminhos jurídicos alternativos para o caso (não redige petição).

    Se `citacoes_candidatas` for informado, cada uma é verificada (ver
    /api/citacoes/verificar) antes de virar fundamento aceito — só as
    confirmadas entram no `pesquisa_verificada` que o modelo pode citar.
    """
    sessao = sessao_repository.carregar(telefone)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    try:
        resultado = await estrategia_service.gerar(
            sessao,
            objetivo_usuario=corpo.objetivo_usuario,
            num_estrategias=corpo.num_estrategias,
            citacoes_candidatas=corpo.citacoes_candidatas,
            buscar_jurisprudencia_automaticamente=corpo.buscar_jurisprudencia_automaticamente,
            buscar_legislacao_automaticamente=corpo.buscar_legislacao_automaticamente,
            competencia=corpo.competencia,
            pressupostos=corpo.pressupostos,
            checar_pressupostos_automaticamente=corpo.checar_pressupostos_automaticamente,
        )
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return resultado


@router.post("/{telefone}/extrair-fatos", response_model=RespostaExtracaoFatos)
def extrair_fatos_do_caso(telefone: str) -> RespostaExtracaoFatos:
    """
    Roda extrair_fatos usando a conversa real do cliente (só as mensagens
    dele, não as perguntas da assistente) e SALVA o resultado na sessão —
    a partir daqui, gerar_estrategias e a checagem automática de
    pressupostos passam a usar essa versão estruturada em vez do resumo
    raso da triagem.
    """
    sessao = sessao_repository.carregar(telefone)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    return extracao_fatos_service.extrair_e_persistir(sessao)


class EscolherEstrategiaIn(BaseModel):
    estrategia_id: str


@router.post("/{telefone}/escolher-estrategia", response_model=Estrategia)
def escolher_estrategia(telefone: str, corpo: EscolherEstrategiaIn) -> Estrategia:
    """
    Salva qual estratégia (dentre as já geradas por gerar_estrategias) o
    advogado escolheu para este caso. A partir daqui, gerar_peticao usa
    essa estratégia automaticamente para alinhar pedidos e fundamentos —
    ver PeticaoRequest.telefone.
    """
    sessao = sessao_repository.carregar(telefone)
    if sessao is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")

    try:
        return estrategia_service.escolher(sessao, corpo.estrategia_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))