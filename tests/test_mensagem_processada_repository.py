import os

from src.repositories.mensagem_processada_repository import MensagemProcessadaRepository


def test_mensagem_nova_nao_esta_processada(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    repo = MensagemProcessadaRepository(db_path=db_path)

    assert repo.ja_processada("wamid.ABC123") is False


def test_apos_marcar_mensagem_fica_processada(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    repo = MensagemProcessadaRepository(db_path=db_path)

    repo.marcar_processada("wamid.ABC123")

    assert repo.ja_processada("wamid.ABC123") is True


def test_marcar_a_mesma_mensagem_duas_vezes_nao_da_erro(tmp_path):
    db_path = os.path.join(tmp_path, "test.db")
    repo = MensagemProcessadaRepository(db_path=db_path)

    repo.marcar_processada("wamid.ABC123")
    repo.marcar_processada("wamid.ABC123")  # simula reenvio da Meta

    assert repo.ja_processada("wamid.ABC123") is True
