"""
Rotas HTTP do módulo `classificar_caso`.
"""
from fastapi import APIRouter

from ..domain.classificacao_schemas import ClassificarCasoRequest, RespostaClassificacao
from ..services.classificacao_service import classificacao_service

router = APIRouter(prefix="/api/classificacao", tags=["classificacao"])


@router.post("/classificar", response_model=RespostaClassificacao)
def classificar_caso(corpo: ClassificarCasoRequest) -> RespostaClassificacao:
    return classificacao_service.classificar(corpo)
