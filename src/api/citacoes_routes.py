"""
Rotas HTTP do módulo `verificar_citacao`.

Camada: api. Independente de um caso específico — verificação de citação é
uma utilidade que qualquer parte do sistema pode chamar antes de aceitar
uma referência jurídica (numa peça, numa estratégia, etc).
"""
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from ..domain.citacao_schemas import CitacaoEntrada, ResultadoVerificacaoCitacao
from ..services.verificacao_citacao_service import verificacao_citacao_service

router = APIRouter(prefix="/api/citacoes", tags=["citacoes"])


class VerificarCitacoesIn(BaseModel):
    citacoes: List[CitacaoEntrada]


class VerificarCitacoesOut(BaseModel):
    resultados: List[ResultadoVerificacaoCitacao]


@router.post("/verificar", response_model=VerificarCitacoesOut)
async def verificar_citacoes(corpo: VerificarCitacoesIn) -> VerificarCitacoesOut:
    resultados = await verificacao_citacao_service.verificar(corpo.citacoes)
    return VerificarCitacoesOut(resultados=resultados)
