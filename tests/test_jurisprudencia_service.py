import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services import jurisprudencia_service as jurisprudencia_module
from src.services.jurisprudencia_service import JurisprudenciaService


def _resposta_llm(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


@pytest.mark.asyncio
async def test_sem_resultado_de_busca_retorna_lista_vazia_sem_chamar_llm(monkeypatch):
    service = JurisprudenciaService()
    mock_llm = MagicMock()
    service._client.chat.completions.create = mock_llm

    mock_buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(jurisprudencia_module.web_search_client, "buscar", mock_buscar)

    resultado = await service.buscar("responsabilidade civil banco cobrança indevida")

    assert resultado == []
    mock_llm.assert_not_called()


@pytest.mark.asyncio
async def test_extrai_candidatos_a_partir_dos_resultados(monkeypatch):
    service = JurisprudenciaService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "citacoes": [
                    {"tipo": "sumula", "referencia": "Súmula 297 STJ", "trecho_citado": None},
                    {"tipo": "acordao", "referencia": "REsp 1.061.530/RS", "trecho_citado": "..."},
                ]
            }
        )
    )

    mock_buscar = AsyncMock(
        return_value=[
            {
                "titulo": "Súmula 297 STJ - aplicação do CDC a bancos",
                "url": "https://stj.jus.br/sumula-297",
                "conteudo": "O Código de Defesa do Consumidor é aplicável às instituições financeiras.",
            }
        ]
    )
    monkeypatch.setattr(jurisprudencia_module.web_search_client, "buscar", mock_buscar)

    candidatos = await service.buscar("CDC aplicável a bancos", tribunais=["STJ"])

    assert len(candidatos) == 2
    assert candidatos[0].referencia == "Súmula 297 STJ"
    assert candidatos[1].tipo.value == "acordao"


@pytest.mark.asyncio
async def test_busca_restringe_dominio_quando_tribunal_conhecido(monkeypatch):
    service = JurisprudenciaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm({"citacoes": []}))

    mock_buscar = AsyncMock(return_value=[{"titulo": "x", "url": "https://stj.jus.br/x", "conteudo": "x"}])
    monkeypatch.setattr(jurisprudencia_module.web_search_client, "buscar", mock_buscar)

    await service.buscar("prazo prescricional", tribunais=["STJ", "TRIBUNAL_DESCONHECIDO"])

    kwargs = mock_buscar.call_args.kwargs
    assert kwargs["include_domains"] == ["stj.jus.br"]


@pytest.mark.asyncio
async def test_json_invalido_do_llm_retorna_lista_vazia(monkeypatch):
    service = JurisprudenciaService()
    resposta_invalida = MagicMock(content="não é json")
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=resposta_invalida)])
    )

    mock_buscar = AsyncMock(return_value=[{"titulo": "x", "url": "https://x.com", "conteudo": "x"}])
    monkeypatch.setattr(jurisprudencia_module.web_search_client, "buscar", mock_buscar)

    candidatos = await service.buscar("qualquer coisa")

    assert candidatos == []
