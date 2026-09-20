"""
Rotas HTTP do módulo `calcular_custas` (determinístico, sem IA).
"""
from fastapi import APIRouter

from ..domain.custas_schemas import CalcularCustasRequest, RespostaCustas
from ..services.calculo_custas_service import calculo_custas_service

router = APIRouter(prefix="/api/custas", tags=["custas"])


@router.post("/calcular", response_model=RespostaCustas)
def calcular_custas(corpo: CalcularCustasRequest) -> RespostaCustas:
    return calculo_custas_service.calcular(corpo)
