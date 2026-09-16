import os

from src.repositories.session_repository import SessaoRepository


def test_obter_ou_criar_gera_sessao_nova(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    repo = SessaoRepository(db_path=db_path)

    sessao = repo.obter_ou_criar("5511999999999")

    assert sessao.telefone == "5511999999999"
    assert sessao.consentimento_lgpd is False
    assert sessao.historico == []


def test_salvar_e_carregar_preserva_dados(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    repo = SessaoRepository(db_path=db_path)

    sessao = repo.obter_ou_criar("5511999999999")
    sessao.consentimento_lgpd = True
    repo.salvar(sessao)

    recarregada = repo.carregar("5511999999999")
    assert recarregada is not None
    assert recarregada.consentimento_lgpd is True