import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.schemas import (
    AreaDireito,
    DadosContato,
    ResumoTriagem,
    SessaoConversa,
    Urgencia,
)
from src.services import pesquisa_juridica_service as pesquisa_module
from src.services.pesquisa_juridica_service import PesquisaJuridicaService


def _criar_sessao() -> SessaoConversa:
    return SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217", nome="Cliente Teste"),
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.TRABALHISTA,
            resumo_caso="Demissão sem justa causa em março de 2024.",
            urgencia=Urgencia.MEDIA,
        ),
    )


def _resposta_sem_ferramenta(texto: str):
    msg = MagicMock(content=texto, tool_calls=None)
    return MagicMock(choices=[MagicMock(message=msg)])


def _resposta_com_ferramenta(query: str, call_id: str = "call_1"):
    tool_call = MagicMock()
    tool_call.id = call_id
    tool_call.function.arguments = json.dumps({"query": query})
    tool_call.model_dump.return_value = {
        "id": call_id,
        "type": "function",
        "function": {"name": "buscar_na_web", "arguments": tool_call.function.arguments},
    }
    msg = MagicMock(content=None, tool_calls=[tool_call])
    return MagicMock(choices=[MagicMock(message=msg)])


@pytest.mark.asyncio
async def test_pergunta_simples_sem_precisar_de_busca(monkeypatch):
    service = PesquisaJuridicaService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_sem_ferramenta("Recomendo pleitear verbas rescisórias e FGTS.")
    )

    sessao = _criar_sessao()
    resposta = await service.perguntar(sessao, "Quais verbas o cliente pode pleitear?")

    assert resposta == "Recomendo pleitear verbas rescisórias e FGTS."
    # a pergunta e a resposta ficam registradas no histórico de pesquisa
    assert len(sessao.historico_pesquisa) == 2
    assert sessao.historico_pesquisa[0].remetente == "advogado"
    assert sessao.historico_pesquisa[1].remetente == "assistente_pesquisa"


@pytest.mark.asyncio
async def test_pergunta_que_aciona_busca_na_web(monkeypatch):
    service = PesquisaJuridicaService()
    service._client.chat.completions.create = MagicMock(
        side_effect=[
            _resposta_com_ferramenta("prazo prescricional ação trabalhista 2026"),
            _resposta_sem_ferramenta("O prazo prescricional é de 2 anos após o fim do contrato."),
        ]
    )

    mock_buscar = AsyncMock(
        return_value=[
            {
                "titulo": "Prescrição trabalhista - artigo",
                "url": "https://exemplo.com/artigo",
                "conteudo": "O prazo prescricional trabalhista é de dois anos...",
            }
        ]
    )
    monkeypatch.setattr(pesquisa_module.web_search_client, "buscar", mock_buscar)

    sessao = _criar_sessao()
    resposta = await service.perguntar(sessao, "Qual o prazo prescricional desse caso?")

    assert "2 anos" in resposta
    mock_buscar.assert_awaited_once_with("prazo prescricional ação trabalhista 2026")
    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_contexto_do_caso_e_enviado_ao_modelo(monkeypatch):
    service = PesquisaJuridicaService()
    mock_create = MagicMock(return_value=_resposta_sem_ferramenta("ok"))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    await service.perguntar(sessao, "Alguma sugestão?")

    mensagens_enviadas = mock_create.call_args.kwargs["messages"]
    contexto = "\n".join(m["content"] for m in mensagens_enviadas if m["role"] == "system")
    assert "Demissão sem justa causa" in contexto
    assert "trabalhista" in contexto
