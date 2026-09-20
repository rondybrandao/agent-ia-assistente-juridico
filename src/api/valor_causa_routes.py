"""
Rotas HTTP do módulo `calcular_valor_causa` (determinístico, sem IA).
"""
from fastapi import APIRouter

from ..domain.valor_causa_schemas import CalcularValorCausaRequest, RespostaValorCausa
from ..services.calculo_valor_causa_service import calculo_valor_causa_service

router = APIRouter(prefix="/api/valor-causa", tags=["valor-causa"])


@router.post("/calcular", response_model=RespostaValorCausa)
def calcular_valor_causa(corpo: CalcularValorCausaRequest) -> RespostaValorCausa:
    return calculo_valor_causa_service.calcular(corpo)
