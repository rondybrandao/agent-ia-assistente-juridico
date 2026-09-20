import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.schemas import (
    AreaDireito,
    DadosContato,
    ResumoTriagem,
    SessaoConversa,
    StatusCaso,
    Urgencia,
)
from src.repositories.session_repository import SessaoRepository
from src.services import advogado_service as advogado_service_module
from src.services.advogado_service import AdvogadoService


@pytest.fixture
def repo_com_caso(tmp_path, monkeypatch):
    """Cria um repositório de teste com um caso já encaminhado e o injeta
    no módulo do AdvogadoService (que usa a instância padrão importada)."""
    db_path = os.path.join(tmp_path, "test.db")
    repo = SessaoRepository(db_path=db_path)

    sessao = SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217", nome="Cliente Teste"),
        status_caso=StatusCaso.ENCAMINHADO,
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.TRABALHISTA,
            resumo_caso="Demissão sem justa causa em março de 2024.",
            urgencia=Urgencia.MEDIA,
            fatos_relevantes=["Carteira assinada"],
            pronto_para_advogado=True,
        ),
    )
    repo.salvar(sessao)

    monkeypatch.setattr(advogado_service_module, "sessao_repository", repo)
    return repo


@pytest.mark.asyncio
async def test_comando_casos_lista_casos_pendentes(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "casos")

    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "5592984705217" in texto_enviado
    assert "trabalhista" in texto_enviado


@pytest.mark.asyncio
async def test_comando_ver_mostra_detalhes_do_caso(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "ver 5592984705217")

    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Demissão sem justa causa" in texto_enviado
    assert "Carteira assinada" in texto_enviado


@pytest.mark.asyncio
async def test_comando_ver_encontra_por_sufixo_do_telefone(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    # advogado digita só os últimos dígitos, sem código do país
    await service.processar_comando("5511888887777", "ver 984705217")

    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Demissão sem justa causa" in texto_enviado


@pytest.mark.asyncio
async def test_comando_anotar_registra_anotacao(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando(
        "5511888887777", "anotar 5592984705217 Enviar notificação extrajudicial"
    )

    sessao = repo_com_caso.carregar("5592984705217")
    assert len(sessao.anotacoes_advogado) == 1
    assert sessao.anotacoes_advogado[0].texto == "Enviar notificação extrajudicial"


@pytest.mark.asyncio
async def test_comando_status_atualiza_status_do_caso(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "status 5592984705217 em_andamento")

    sessao = repo_com_caso.carregar("5592984705217")
    assert sessao.status_caso == StatusCaso.EM_ANDAMENTO


@pytest.mark.asyncio
async def test_comando_status_invalido_nao_altera_nada(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "status 5592984705217 finalizadissimo")

    sessao = repo_com_caso.carregar("5592984705217")
    assert sessao.status_caso == StatusCaso.ENCAMINHADO  # não mudou
    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "inválido" in texto_enviado.lower()


@pytest.mark.asyncio
async def test_comando_desconhecido_mostra_ajuda(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "oi tudo bem?")

    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Comandos disponíveis" in texto_enviado


@pytest.mark.asyncio
async def test_ver_caso_inexistente_retorna_mensagem_clara(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "ver 0000000000")

    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Nenhum caso encontrado" in texto_enviado


@pytest.mark.asyncio
async def test_comando_estrategias_gera_e_formata_a_resposta(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    from src.domain.estrategia_schemas import (
        Estrategia,
        EstimativaCusto,
        EstimativaPrazo,
        RespostaEstrategias,
        TutelaUrgencia,
    )

    resposta_falsa = RespostaEstrategias(
        estrategias=[
            Estrategia(
                id="A",
                nome="Juizado Especial",
                via="judicial",
                rito="juizado_especial",
                eixos_de_diferenca=["RITO", "ESCOPO"],
                resumo="Ação enxuta no JEC.",
                tutela_urgencia=TutelaUrgencia(cabivel=False, justificativa="sem urgência"),
                pontos_fortes=["Rápido"],
                riscos=["Teto de valor"],
                estimativa_custo=EstimativaCusto(custas="Isento", honorarios_sucumbencia="N/A", observacao=""),
                estimativa_prazo=EstimativaPrazo(faixa="3-6 meses", base="estimativa qualitativa"),
                probabilidade_qualitativa="media",
                justificativa_probabilidade="Fatos bem documentados.",
                quando_escolher="Quando o objetivo é rapidez.",
            )
        ],
        aviso="A decisão final é do advogado responsável.",
    )
    mock_gerar = AsyncMock(return_value=resposta_falsa)
    monkeypatch.setattr(advogado_service_module.estrategia_service, "gerar", mock_gerar)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "estrategias 5592984705217 rapidez")

    mock_gerar.assert_called_once()
    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Juizado Especial" in texto_enviado
    assert "responsável" in texto_enviado


@pytest.mark.asyncio
async def test_comando_fatos_extrai_e_formata_a_resposta(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    from src.domain.fatos_schemas import EventoLinhaDoTempo, RespostaExtracaoFatos

    resultado_falso = RespostaExtracaoFatos(
        resumo_narrativo="Cliente relata cobrança indevida.",
        linha_do_tempo=[
            EventoLinhaDoTempo(
                data=None, data_aproximada_texto="março de 2024", descricao="Cobrança percebida", fonte="relato"
            )
        ],
    )
    mock_extrair = MagicMock(return_value=resultado_falso)
    monkeypatch.setattr(advogado_service_module.extracao_fatos_service, "extrair_e_persistir", mock_extrair)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "fatos 5592984705217")

    mock_extrair.assert_called_once()
    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Cobrança percebida" in texto_enviado
    assert "estrategias" in texto_enviado.lower()


@pytest.mark.asyncio
async def test_comando_fatos_com_telefone_inexistente(repo_com_caso, monkeypatch):
    mock_whatsapp = AsyncMock()
    monkeypatch.setattr(advogado_service_module.whatsapp_client, "enviar_mensagem_texto", mock_whatsapp)

    service = AdvogadoService()
    await service.processar_comando("5511888887777", "fatos 0000000000")

    texto_enviado = mock_whatsapp.call_args[0][1]
    assert "Nenhum caso encontrado" in texto_enviado