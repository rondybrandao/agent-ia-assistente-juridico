import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.citacao_schemas import CitacaoEntrada, StatusVerificacao, TipoCitacao
from src.services import verificacao_citacao_service as service_module
from src.services.verificacao_citacao_service import VerificacaoCitacaoService


def _resposta_llm(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


@pytest.mark.asyncio
async def test_sem_resultado_de_busca_nunca_confirma_e_nao_chama_llm(monkeypatch):
    service = VerificacaoCitacaoService()
    mock_llm = MagicMock()
    service._client.chat.completions.create = mock_llm

    mock_buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(service_module.web_search_client, "buscar", mock_buscar)

    citacao = CitacaoEntrada(tipo=TipoCitacao.SUMULA, referencia="Súmula 999999 STJ")
    resultado = await service.verificar_uma(citacao)

    assert resultado.status == StatusVerificacao.INCONCLUSIVA
    assert resultado.existe is False
    mock_llm.assert_not_called()  # não gasta chamada de LLM sem evidência nenhuma


@pytest.mark.asyncio
async def test_citacao_confirmada_com_evidencia_forte(monkeypatch):
    service = VerificacaoCitacaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "status": "confirmada",
                "existe": True,
                "trecho_confere": True,
                "vigente": True,
                "fonte_url": "https://stj.jus.br/sumula-297",
                "observacao": "Resultado oficial do STJ confirma texto e vigência.",
            }
        )
    )

    mock_buscar = AsyncMock(
        return_value=[
            {
                "titulo": "Súmula 297 STJ",
                "url": "https://stj.jus.br/sumula-297",
                "conteudo": "O Código de Defesa do Consumidor é aplicável às instituições financeiras.",
            }
        ]
    )
    monkeypatch.setattr(service_module.web_search_client, "buscar", mock_buscar)

    citacao = CitacaoEntrada(tipo=TipoCitacao.SUMULA, referencia="Súmula 297 STJ")
    resultado = await service.verificar_uma(citacao)

    assert resultado.status == StatusVerificacao.CONFIRMADA
    assert resultado.existe is True
    assert resultado.fonte_url == "https://stj.jus.br/sumula-297"


@pytest.mark.asyncio
async def test_citacao_nao_encontrada_quando_busca_nao_confirma(monkeypatch):
    service = VerificacaoCitacaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "status": "nao_encontrada",
                "existe": False,
                "trecho_confere": None,
                "vigente": None,
                "fonte_url": None,
                "observacao": "Nenhum resultado menciona esse número de acórdão.",
            }
        )
    )

    mock_buscar = AsyncMock(
        return_value=[
            {"titulo": "Página não relacionada", "url": "https://exemplo.com", "conteudo": "conteúdo qualquer"}
        ]
    )
    monkeypatch.setattr(service_module.web_search_client, "buscar", mock_buscar)

    citacao = CitacaoEntrada(tipo=TipoCitacao.ACORDAO, referencia="REsp 9.999.999/XX")
    resultado = await service.verificar_uma(citacao)

    assert resultado.status == StatusVerificacao.NAO_ENCONTRADA
    assert resultado.existe is False


@pytest.mark.asyncio
async def test_retentativa_quando_llm_devolve_json_invalido(monkeypatch):
    service = VerificacaoCitacaoService()
    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[
            resposta_invalida_msg,
            _resposta_llm(
                {
                    "status": "confirmada",
                    "existe": True,
                    "trecho_confere": None,
                    "vigente": True,
                    "fonte_url": "https://planalto.gov.br/lei8078",
                    "observacao": "Lei encontrada no Planalto.",
                }
            ),
        ]
    )

    mock_buscar = AsyncMock(
        return_value=[{"titulo": "Lei 8.078/1990", "url": "https://planalto.gov.br/lei8078", "conteudo": "..."}]
    )
    monkeypatch.setattr(service_module.web_search_client, "buscar", mock_buscar)

    citacao = CitacaoEntrada(tipo=TipoCitacao.LEI, referencia="Lei 8.078/1990")
    resultado = await service.verificar_uma(citacao)

    assert resultado.status == StatusVerificacao.CONFIRMADA
    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_falha_persistente_do_llm_vira_inconclusiva_nao_confirmada(monkeypatch):
    service = VerificacaoCitacaoService()
    resposta_invalida = MagicMock(content="ainda inválido")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])
    service._client.chat.completions.create = MagicMock(return_value=resposta_invalida_msg)

    mock_buscar = AsyncMock(return_value=[{"titulo": "x", "url": "https://x.com", "conteudo": "x"}])
    monkeypatch.setattr(service_module.web_search_client, "buscar", mock_buscar)

    citacao = CitacaoEntrada(tipo=TipoCitacao.LEI, referencia="Lei 1.234/2020")
    resultado = await service.verificar_uma(citacao)

    # Nunca deve "confirmar por padrão" quando algo dá errado.
    assert resultado.status == StatusVerificacao.INCONCLUSIVA
    assert resultado.existe is False


@pytest.mark.asyncio
async def test_verificar_lista_processa_todas_as_citacoes(monkeypatch):
    service = VerificacaoCitacaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "status": "confirmada",
                "existe": True,
                "trecho_confere": None,
                "vigente": True,
                "fonte_url": "https://x.com",
                "observacao": "ok",
            }
        )
    )
    mock_buscar = AsyncMock(return_value=[{"titulo": "x", "url": "https://x.com", "conteudo": "x"}])
    monkeypatch.setattr(service_module.web_search_client, "buscar", mock_buscar)

    citacoes = [
        CitacaoEntrada(tipo=TipoCitacao.LEI, referencia="Lei 8.078/1990"),
        CitacaoEntrada(tipo=TipoCitacao.SUMULA, referencia="Súmula 297 STJ"),
    ]
    resultados = await service.verificar(citacoes)

    assert len(resultados) == 2
    assert all(r.status == StatusVerificacao.CONFIRMADA for r in resultados)
