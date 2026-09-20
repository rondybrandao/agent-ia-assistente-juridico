"""
Rotas HTTP do módulo `extrair_fatos`.
"""
from fastapi import APIRouter

from ..domain.fatos_schemas import ExtrairFatosRequest, RespostaExtracaoFatos
from ..services.extracao_fatos_service import extracao_fatos_service

router = APIRouter(prefix="/api/fatos", tags=["fatos"])


@router.post("/extrair", response_model=RespostaExtracaoFatos)
def extrair_fatos(corpo: ExtrairFatosRequest) -> RespostaExtracaoFatos:
    return extracao_fatos_service.extrair(corpo)
