"""
Cliente para a WhatsApp Cloud API (Meta) oficial.

Camada: integrations — isola tudo que fala com serviços externos. Trocar
Meta Cloud API por um BSP (Twilio, 360dialog, Z-API) significa reescrever
só este arquivo, mantendo a mesma interface pública (enviar_mensagem_texto /
extrair_mensagem_recebida) usada pelo resto do sistema.
"""
from typing import Optional, Tuple

import httpx

from ..core.config import settings


class WhatsAppClient:
    def __init__(self) -> None:
        self._base_url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )
        self._headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        }

    async def enviar_mensagem_texto(self, telefone_destino: str, texto: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": telefone_destino,
            "type": "text",
            "text": {"body": texto},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self._base_url, headers=self._headers, json=payload)
            r.raise_for_status()

    @staticmethod
    def extrair_mensagem_recebida(payload: dict) -> Optional[Tuple[str, str]]:
        """
        Extrai (telefone_remetente, texto) de um payload de webhook da Meta.
        Retorna None se não houver mensagem de texto de usuário (ex.: status
        de entrega/leitura ou outro tipo de evento).
        """
        try:
            entry = payload["entry"][0]
            change = entry["changes"][0]["value"]
            mensagens = change.get("messages")
            if not mensagens:
                return None
            msg = mensagens[0]
            if msg.get("type") != "text":
                return None
            return msg["from"], msg["text"]["body"]
        except (KeyError, IndexError, TypeError):
            return None


# instância padrão usada pela aplicação
whatsapp_client = WhatsAppClient()