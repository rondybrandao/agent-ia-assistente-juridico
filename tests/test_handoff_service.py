import json
from unittest.mock import AsyncMock

import pytest

from src.domain.schemas import (
    AreaDireito,
    DadosContato,
    ResumoTriagem,
    SessaoConversa,
    Urgencia,
)
from src.services import handoff_service as handoff_service_module
from src.services.handoff_service import HandoffService


def _criar_sessao_com_resumo() -> SessaoConversa:
    return SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217", nome="Cliente Teste"),
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.TRABALHISTA,
            resumo_caso="Demissão sem justa causa em março de 2024.",
            urgencia=Urgencia.MEDIA,
            fatos_relevantes=["Carteira assinada", "Trabalhou 2 anos"],
            pronto_para_advogado=True,
        ),
    )


@pytest.mark.asyncio
async def test_encaminhar_envia_whatsapp_para_advogado_quando_configurado(monkeypatch, tmp_path):
    monkeypatch.setattr(handoff_service_module.settings, "ADVOGADO_WHATSAPP_NUMERO", "5511888887777")
    monkeypatch.setattr(handoff_service_module.settings, "WEBHOOK_INTERNO_HANDOFF", "")

    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(
        handoff_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp
    )

    log_path = str(tmp_path / "handoffs.log.jsonl")
    service = HandoffService(log_path=log_path)
    sessao = _criar_sessao_com_resumo()

    await service.encaminhar(sessao)

    mock_whatsapp.assert_awaited_once()
    telefone_enviado, texto_enviado = mock_whatsapp.call_args[0]
    assert telefone_enviado == "5511888887777"
    assert "trabalhista" in texto_enviado
    assert "Demissão sem justa causa" in texto_enviado


@pytest.mark.asyncio
async def test_encaminhar_grava_log_mesmo_sem_whatsapp_configurado(monkeypatch, tmp_path):
    monkeypatch.setattr(handoff_service_module.settings, "ADVOGADO_WHATSAPP_NUMERO", "")
    monkeypatch.setattr(handoff_service_module.settings, "WEBHOOK_INTERNO_HANDOFF", "")

    log_path = str(tmp_path / "handoffs.log.jsonl")
    service = HandoffService(log_path=log_path)
    sessao = _criar_sessao_com_resumo()

    await service.encaminhar(sessao)

    with open(log_path, encoding="utf-8") as f:
        linha = json.loads(f.readline())
    assert linha["telefone"] == "5592984705217"
    assert linha["resumo"]["area_direito"] == "trabalhista"


@pytest.mark.asyncio
async def test_falha_no_whatsapp_nao_impede_gravacao_do_log(monkeypatch, tmp_path):
    monkeypatch.setattr(handoff_service_module.settings, "ADVOGADO_WHATSAPP_NUMERO", "5511888887777")
    monkeypatch.setattr(handoff_service_module.settings, "WEBHOOK_INTERNO_HANDOFF", "")

    mock_whatsapp = AsyncMock(side_effect=Exception("erro de rede simulado"))
    monkeypatch.setattr(
        handoff_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp
    )

    log_path = str(tmp_path / "handoffs.log.jsonl")
    service = HandoffService(log_path=log_path)
    sessao = _criar_sessao_com_resumo()

    await service.encaminhar(sessao)  # não deve levantar exceção

    with open(log_path, encoding="utf-8") as f:
        linha = json.loads(f.readline())
    assert linha["telefone"] == "5592984705217"
