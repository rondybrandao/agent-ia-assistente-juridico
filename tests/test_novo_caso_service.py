from unittest.mock import MagicMock

import pytest

from src.domain.schemas import AreaDireito, ResumoTriagem, StatusCaso, Urgencia
from src.repositories.session_repository import SessaoRepository
from src.services import novo_caso_service as modulo
from src.services.novo_caso_service import NovoCasoService


@pytest.fixture
def repo_teste(tmp_path, monkeypatch):
    repo = SessaoRepository(db_path=str(tmp_path / "test.db"))
    monkeypatch.setattr(modulo, "sessao_repository", repo)
    return repo


def test_primeira_mensagem_cria_caso_novo_com_id_gerado(repo_teste):
    service = NovoCasoService()
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Entendi, me conte mais."))])
    )
    mock_llm_engine = MagicMock()
    mock_llm_engine.extrair_resumo_estruturado.return_value = ResumoTriagem(
        area_direito=AreaDireito.CONSUMIDOR, urgencia=Urgencia.MEDIA
    )
    import src.services.novo_caso_service as mod

    mod.llm_engine = mock_llm_engine

    resposta, sessao = service.processar_mensagem(None, "Cliente foi cobrado indevidamente.")

    assert sessao.telefone.startswith("manual-")
    assert sessao.encaminhada_advogado is True
    assert sessao.status_caso == StatusCaso.ENCAMINHADO
    assert resposta == "Entendi, me conte mais."
    assert len(sessao.historico) == 2  # usuário + assistente

    # confirma que já foi persistido de verdade
    recarregada = repo_teste.carregar(sessao.telefone)
    assert recarregada is not None


def test_segunda_mensagem_usa_o_mesmo_case_id(repo_teste, monkeypatch):
    service = NovoCasoService()
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Ok"))])
    )
    mock_llm_engine = MagicMock()
    mock_llm_engine.extrair_resumo_estruturado.return_value = ResumoTriagem()
    monkeypatch.setattr(modulo, "llm_engine", mock_llm_engine)

    _, sessao1 = service.processar_mensagem(None, "Primeira mensagem.")
    case_id = sessao1.telefone

    _, sessao2 = service.processar_mensagem(case_id, "Segunda mensagem.")

    assert sessao2.telefone == case_id
    assert len(sessao2.historico) == 4  # 2 mensagens x (usuário + assistente)


def test_case_id_inexistente_levanta_erro(repo_teste):
    service = NovoCasoService()
    with pytest.raises(ValueError):
        service.processar_mensagem("manual-naoexiste", "Qualquer coisa")


def test_falha_na_extracao_nao_impede_a_resposta(repo_teste, monkeypatch):
    """Se a extração estruturada falhar, a conversa continua (o resumo só
    não é atualizado nessa rodada) — não pode travar o chat inteiro."""
    service = NovoCasoService()
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=MagicMock(content="Resposta normal"))])
    )
    mock_llm_engine = MagicMock()
    mock_llm_engine.extrair_resumo_estruturado.side_effect = Exception("erro simulado")
    monkeypatch.setattr(modulo, "llm_engine", mock_llm_engine)

    resposta, sessao = service.processar_mensagem(None, "Mensagem qualquer")

    assert resposta == "Resposta normal"
    assert sessao.telefone.startswith("manual-")  # não travou, caso foi criado normalmente
