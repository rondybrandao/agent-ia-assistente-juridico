import pytest
from src.services.triage_service import _eh_confirmacao_positiva


@pytest.mark.parametrize("texto,esperado", [
    ("sim", True),
    ("Sim, concordo", True),
    ("  OK  ", True),
    ("não quero", False),
    ("", False),
    ("talvez", False),
])
def test_eh_confirmacao_positiva(texto, esperado):
    assert _eh_confirmacao_positiva(texto) == esperado