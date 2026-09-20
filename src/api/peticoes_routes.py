"""
Rotas HTTP do módulo `gerar_peticao`.

Camada: api. Independente de um caso específico da triagem — o advogado
pode gerar uma peça a partir de qualquer combinação de dados, não só dos
casos que vieram pelo WhatsApp.
"""
from typing import List

from fastapi import APIRouter, HTTPException, Response

from ..domain.peca_acessoria_schemas import PecaAcessoriaRequest
from ..domain.peticao_schemas import PeticaoRequest, PeticaoResponse
from ..domain.revisao_schemas import ChecklistDisponivel, RespostaRevisao
from ..services.exportacao_service import exportacao_service
from ..services.peca_acessoria_service import peca_acessoria_service
from ..services.peticao_service import peticao_service
from ..services.revisao_peticao_service import revisao_peticao_service

router = APIRouter(prefix="/api/peticoes", tags=["peticoes"])


@router.get("/templates")
def listar_templates() -> List[dict]:
    return peticao_service.listar_templates()


@router.post("/gerar", response_model=PeticaoResponse)
async def gerar_peticao(corpo: PeticaoRequest) -> PeticaoResponse:
    """
    Gera um RASCUNHO de petição a partir de um template. Sempre exige
    revisão humana antes de qualquer uso — ver o campo "aviso" da resposta
    e a lista "campos_pendentes" (dados que faltaram e precisam ser
    completados manualmente).
    """
    try:
        return await peticao_service.gerar(corpo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{peca_id}/revisar", response_model=RespostaRevisao)
async def revisar_peticao(peca_id: str, checklist: ChecklistDisponivel) -> RespostaRevisao:
    """Roda um checklist legal (CPC art. 319/320, CLT art. 840, ritos dos
    Juizados) sobre a peça. Nunca substitui a revisão do advogado."""
    try:
        return await revisao_peticao_service.revisar(peca_id, checklist)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{peca_id}/exportar")
def exportar_peticao(peca_id: str, formato: str) -> Response:
    """Exporta a peça em .docx ou .pdf. Use formato=docx ou formato=pdf."""
    try:
        resultado = exportacao_service.exportar(peca_id, [formato])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    conteudo = resultado[formato]
    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    return Response(
        content=conteudo,
        media_type=media_types[formato],
        headers={"Content-Disposition": f'attachment; filename="peticao_{peca_id}.{formato}"'},
    )


@router.get("/pecas-acessorias/templates")
def listar_pecas_acessorias() -> List[dict]:
    return peca_acessoria_service.listar_templates()


@router.post("/pecas-acessorias/gerar", response_model=PeticaoResponse)
async def gerar_peca_acessoria(corpo: PecaAcessoriaRequest) -> PeticaoResponse:
    """
    Gera procuração, declaração de hipossuficiência, notificação
    extrajudicial ou rol de documentos. A peça gerada usa o mesmo peca_id
    de gerar_peticao — ou seja, pode ser exportada em .docx/PDF pelo mesmo
    endpoint GET /{peca_id}/exportar.
    """
    try:
        return await peca_acessoria_service.gerar(corpo)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))