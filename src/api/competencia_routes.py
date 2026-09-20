"""
Rotas HTTP do módulo `definir_competencia` (determinístico, sem IA).
"""
from fastapi import APIRouter

from ..domain.competencia_schemas import DefinirCompetenciaRequest, RespostaCompetencia
from ..services.competencia_service import competencia_service

router = APIRouter(prefix="/api/competencia", tags=["competencia"])


@router.post("/definir", response_model=RespostaCompetencia)
def definir_competencia(corpo: DefinirCompetenciaRequest) -> RespostaCompetencia:
    return competencia_service.definir(corpo)
