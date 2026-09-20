"""
Testes do TriageService com todas as dependências externas mockadas:
não chamamos WhatsApp, SQLite nem a API do LLM de verdade.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.schemas import DadosContato, DadosPessoaisAutor, ResumoTriagem, SessaoConversa, Urgencia
from src.integrations.whatsapp_client import WhatsAppClient
from src.services import triage_service as triage_service_module
from src.services.triage_service import TriageService


def _criar_sessao(telefone: str = "5511999999999", consentimento: bool = False) -> SessaoConversa:
    return SessaoConversa(
        telefone=telefone,
        contato=DadosContato(telefone=telefone),
        consentimento_lgpd=consentimento,
    )


def _mockar_dependencias(monkeypatch, sessao: SessaoConversa):
    """Substitui as 4 dependências externas do TriageService por mocks."""
    mock_repo = MagicMock(obter_ou_criar=MagicMock(return_value=sessao), salvar=MagicMock())
    monkeypatch.setattr(triage_service_module, "sessao_repository", mock_repo)

    mock_llm = MagicMock()
    monkeypatch.setattr(triage_service_module, "llm_engine", mock_llm)

    mock_whatsapp = MagicMock(
        enviar_mensagem_texto=AsyncMock(),
        # usa a normalização REAL (não um mock genérico), senão a comparação
        # de telefones em _eh_mensagem_do_advogado fica quebrada: um mock
        # genérico sempre devolve o mesmo objeto, não importa o argumento.
        normalizar_numero_brasileiro=WhatsAppClient.normalizar_numero_brasileiro,
    )
    monkeypatch.setattr(triage_service_module, "whatsapp_client", mock_whatsapp)

    mock_handoff = MagicMock(encaminhar=AsyncMock())
    monkeypatch.setattr(triage_service_module, "handoff_service", mock_handoff)

    return mock_repo, mock_llm, mock_whatsapp, mock_handoff


@pytest.mark.asyncio
async def test_primeira_mensagem_pede_consentimento_e_nao_extrai_resumo(monkeypatch):
    # Arrange
    sessao = _criar_sessao(consentimento=False)
    _, mock_llm, mock_whatsapp, mock_handoff = _mockar_dependencias(monkeypatch, sessao)
    mock_llm.gerar_resposta_conversa.return_value = "Oi! Você concorda em prosseguir?"

    service = TriageService()

    # Act
    await service.processar_turno("5511999999999", "Olá, fui demitido")

    # Assert
    mock_whatsapp.enviar_mensagem_texto.assert_awaited_once_with(
        "5511999999999", "Oi! Você concorda em prosseguir?"
    )
    mock_llm.extrair_resumo_estruturado.assert_not_called()
    mock_handoff.encaminhar.assert_not_awaited()


@pytest.mark.asyncio
async def test_quando_resumo_esta_pronto_encaminha_para_advogado(monkeypatch):
    # Arrange
    sessao = _criar_sessao(consentimento=True)
    _, mock_llm, mock_whatsapp, mock_handoff = _mockar_dependencias(monkeypatch, sessao)
    mock_llm.gerar_resposta_conversa.return_value = "Entendi, obrigada pelas informações."
    mock_llm.extrair_resumo_estruturado.return_value = ResumoTriagem(
        area_direito="trabalhista",
        urgencia=Urgencia.MEDIA,
        pronto_para_advogado=True,
        dados_pessoais_autor=DadosPessoaisAutor(
            nome="Cliente Teste",
            nacionalidade="brasileira",
            estado_civil="solteiro",
            profissao="motorista",
            cpf="123.456.789-00",
            rg="1234567",
            endereco_completo="Rua X, 123",
            cep="69000-000",
            cidade="Manaus",
            data_nascimento="1990-01-01",
        ),
    )

    service = TriageService()

    # Act
    await service.processar_turno(
        "5511999999999",
        "Fui demitido em 2024 sem justa causa, tenho a carteira assinada",
    )

    # Assert
    mock_handoff.encaminhar.assert_awaited_once()
    assert sessao.encerrada is True
    assert sessao.encaminhada_advogado is True


@pytest.mark.asyncio
async def test_pronto_para_advogado_sozinho_nao_basta_sem_qualificacao_completa(monkeypatch):
    """A trava determinística: mesmo se a IA disser pronto_para_advogado=True,
    sem a qualificação completa o caso NÃO pode ser encaminhado."""
    sessao = _criar_sessao(consentimento=True)
    _, mock_llm, mock_whatsapp, mock_handoff = _mockar_dependencias(monkeypatch, sessao)
    mock_llm.gerar_resposta_conversa.return_value = "Só preciso do seu CPF e endereço ainda."
    mock_llm.extrair_resumo_estruturado.return_value = ResumoTriagem(
        area_direito="trabalhista",
        urgencia=Urgencia.MEDIA,
        pronto_para_advogado=True,  # a IA "acha" que está pronto...
        dados_pessoais_autor=DadosPessoaisAutor(nome="Cliente Teste"),  # ...mas falta quase tudo
    )

    service = TriageService()

    await service.processar_turno("5511999999999", "Me chamo Cliente Teste")

    mock_handoff.encaminhar.assert_not_awaited()
    assert sessao.encerrada is False


@pytest.mark.asyncio
async def test_urgencia_critica_encaminha_mesmo_sem_qualificacao_completa(monkeypatch):
    """Urgência crítica é a única exceção que pula a exigência de
    qualificação completa — não faz sentido segurar um caso de risco."""
    sessao = _criar_sessao(consentimento=True)
    _, mock_llm, mock_whatsapp, mock_handoff = _mockar_dependencias(monkeypatch, sessao)
    mock_llm.gerar_resposta_conversa.return_value = "Isso é muito sério, já vou encaminhar."
    mock_llm.extrair_resumo_estruturado.return_value = ResumoTriagem(
        area_direito="penal",
        urgencia=Urgencia.CRITICA,
        motivo_urgencia="Prisão em flagrante",
        pronto_para_advogado=False,  # nem a IA marcou como pronto...
        dados_pessoais_autor=DadosPessoaisAutor(),  # ...e não tem nenhum dado pessoal ainda
    )

    service = TriageService()

    await service.processar_turno("5511999999999", "Meu marido acabou de ser preso")

    mock_handoff.encaminhar.assert_awaited_once()
    assert sessao.encerrada is True


@pytest.mark.asyncio
async def test_sessao_ja_encerrada_nao_chama_llm(monkeypatch):
    # Arrange: sessão que já foi encaminhada anteriormente
    sessao = _criar_sessao(consentimento=True)
    sessao.encerrada = True
    _, mock_llm, mock_whatsapp, mock_handoff = _mockar_dependencias(monkeypatch, sessao)

    service = TriageService()

    # Act
    await service.processar_turno("5511999999999", "Oi, alguém já viu meu caso?")

    # Assert: nem tenta conversar de novo, só avisa que já foi encaminhado
    mock_llm.gerar_resposta_conversa.assert_not_called()
    mock_whatsapp.enviar_mensagem_texto.assert_awaited_once()


@pytest.mark.asyncio
async def test_mensagem_do_advogado_e_roteada_para_advogado_service(monkeypatch):
    # Arrange: mesmo número em dois formatos válidos (com e sem o 9)
    monkeypatch.setattr(triage_service_module.settings, "ADVOGADO_WHATSAPP_NUMERO", "5511987654321")

    mock_advogado_service = MagicMock(processar_comando=AsyncMock())
    monkeypatch.setattr(triage_service_module, "advogado_service", mock_advogado_service)

    mock_llm = MagicMock()
    monkeypatch.setattr(triage_service_module, "llm_engine", mock_llm)

    service = TriageService()

    # Act: mensagem vindo do MESMO número do advogado, mas no formato sem o 9,
    # como às vezes chega no campo 'from' do webhook
    await service.processar_turno("551187654321", "casos")

    # Assert: foi pro modo advogado, não entrou no fluxo de triagem de cliente
    mock_advogado_service.processar_comando.assert_awaited_once_with("551187654321", "casos")
    mock_llm.gerar_resposta_conversa.assert_not_called()


@pytest.mark.asyncio
async def test_mensagem_de_cliente_comum_nao_e_roteada_para_advogado(monkeypatch):
    # Arrange
    monkeypatch.setattr(triage_service_module.settings, "ADVOGADO_WHATSAPP_NUMERO", "5511987654321")

    mock_advogado_service = MagicMock(processar_comando=AsyncMock())
    monkeypatch.setattr(triage_service_module, "advogado_service", mock_advogado_service)

    sessao = _criar_sessao(telefone="5592984705217", consentimento=False)
    _, mock_llm, _, _ = _mockar_dependencias(monkeypatch, sessao)
    mock_llm.gerar_resposta_conversa.return_value = "Olá! Você concorda em prosseguir?"

    service = TriageService()

    # Act: número diferente do advogado
    await service.processar_turno("5592984705217", "Olá, preciso de ajuda")

    # Assert: não foi pro modo advogado
    mock_advogado_service.processar_comando.assert_not_awaited()