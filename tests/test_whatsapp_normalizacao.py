import pytest

from src.integrations.whatsapp_client import WhatsAppClient


@pytest.mark.parametrize("entrada,esperado", [
    ("559284705217", "5592984705217"),   # celular BR sem o 9 -> adiciona
    ("5592984705217", "5592984705217"),  # já tem o 9 -> mantém
    ("15551474533", "15551474533"),      # número americano -> não mexe
    ("551140028922", "551140028922"),    # telefone fixo BR (10 dígitos locais) -> não mexe*
    ("55923584859", "55923584859"),
    ("55993584859", "55993584859"),
    ("559293584859", "5592993584859"),
    ("5592993584859", "5592993584859")
])
def test_normalizar_numero_brasileiro(entrada, esperado):
    assert WhatsAppClient.normalizar_numero_brasileiro(entrada) == esperado
