from src.integrations.whatsapp_client import WhatsAppClient


def test_extrai_mensagem_de_texto_valida():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": "5511999999999",
                                    "type": "text",
                                    "text": {"body": "Olá"},
                                    "id": "wamid.ABC123",
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    assert WhatsAppClient.extrair_mensagem_recebida(payload) == (
        "5511999999999",
        "Olá",
        "wamid.ABC123",
    )


def test_retorna_none_para_evento_de_status():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert WhatsAppClient.extrair_mensagem_recebida(payload) is None


def test_retorna_none_para_payload_invalido():
    assert WhatsAppClient.extrair_mensagem_recebida({}) is None