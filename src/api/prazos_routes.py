"""
Rotas HTTP do módulo `calcular_prazos` (determinístico, sem IA).
"""
from fastapi import APIRouter

from ..domain.prazo_schemas import CalcularPrazoRequest, RespostaPrazo
from ..services.calculo_prazo_service import calculo_prazo_service

router = APIRouter(prefix="/api/prazos", tags=["prazos"])


@router.post("/calcular", response_model=RespostaPrazo)
def calcular_prazo(corpo: CalcularPrazoRequest) -> RespostaPrazo:
    return calculo_prazo_service.calcular(corpo)
