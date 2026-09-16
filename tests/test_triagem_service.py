from src.services.triage_service import _eh_confirmacao_positiva


def test_confirmacao_positiva_simples():
    assert _eh_confirmacao_positiva("sim") == True


def test_confirmacao_negativa():
    assert _eh_confirmacao_positiva("não quero") == False


def test_confirmacao_com_espacos_e_maiusculas():
    assert _eh_confirmacao_positiva("  SIM, concordo  ") == True