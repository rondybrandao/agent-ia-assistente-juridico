"""
Rotas HTTP do módulo `checar_pressupostos`.
"""
from fastapi import APIRouter

from ..domain.pressupostos_schemas import CheckPressupostosRequest, RespostaPressupostos
from ..services.pressupostos_service import checar_pressupostos_service

router = APIRouter(prefix="/api/pressupostos", tags=["pressupostos"])


@router.post("/checar", response_model=RespostaPressupostos)
def checar_pressupostos(corpo: CheckPressupostosRequest) -> RespostaPressupostos:
    return checar_pressupostos_service.checar(corpo)
