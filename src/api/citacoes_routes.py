"""
Rotas HTTP do módulo `verificar_citacao`.

Camada: api. Independente de um caso específico — verificação de citação é
uma utilidade que qualquer parte do sistema pode chamar antes de aceitar
uma referência jurídica (numa peça, numa estratégia, etc).
"""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..domain.citacao_schemas import CitacaoEntrada, ResultadoVerificacaoCitacao
from ..services.jurisprudencia_service import jurisprudencia_service
from ..services.legislacao_service import legislacao_service
from ..services.verificacao_citacao_service import verificacao_citacao_service

router = APIRouter(prefix="/api/citacoes", tags=["citacoes"])


class VerificarCitacoesIn(BaseModel):
    citacoes: List[CitacaoEntrada]


class VerificarCitacoesOut(BaseModel):
    resultados: List[ResultadoVerificacaoCitacao]


class BuscarJurisprudenciaIn(BaseModel):
    consulta: str
    tribunais: Optional[List[str]] = None
    tipo: Optional[List[str]] = None
    limite: int = 10


class BuscarJurisprudenciaOut(BaseModel):
    candidatos: List[CitacaoEntrada]


@router.post("/verificar", response_model=VerificarCitacoesOut)
async def verificar_citacoes(corpo: VerificarCitacoesIn) -> VerificarCitacoesOut:
    resultados = await verificacao_citacao_service.verificar(corpo.citacoes)
    return VerificarCitacoesOut(resultados=resultados)


@router.post("/buscar-jurisprudencia", response_model=BuscarJurisprudenciaOut)
async def buscar_jurisprudencia(corpo: BuscarJurisprudenciaIn) -> BuscarJurisprudenciaOut:
    """
    Busca candidatos de citação (ainda NÃO verificados). Antes de usar
    qualquer resultado numa peça, passe por POST /api/citacoes/verificar.
    """
    candidatos = await jurisprudencia_service.buscar(
        corpo.consulta, tribunais=corpo.tribunais, tipo=corpo.tipo, limite=corpo.limite
    )
    return BuscarJurisprudenciaOut(candidatos=candidatos)


class BuscarLegislacaoIn(BaseModel):
    consulta: str
    norma: Optional[str] = None
    dispositivo: Optional[str] = None
    limite: int = 5


class BuscarLegislacaoOut(BaseModel):
    candidatos: List[CitacaoEntrada]


@router.post("/buscar-legislacao", response_model=BuscarLegislacaoOut)
async def buscar_legislacao(corpo: BuscarLegislacaoIn) -> BuscarLegislacaoOut:
    """
    Busca candidatos de dispositivos legais (ainda NÃO verificados). Antes
    de usar qualquer resultado numa peça, passe por POST /api/citacoes/verificar.
    """
    candidatos = await legislacao_service.buscar(
        corpo.consulta, norma=corpo.norma, dispositivo=corpo.dispositivo, limite=corpo.limite
    )
    return BuscarLegislacaoOut(candidatos=candidatos)