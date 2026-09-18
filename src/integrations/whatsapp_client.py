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
        telefone_destino = self.normalizar_numero_brasileiro(telefone_destino)
        payload = {
            "messaging_product": "whatsapp",
            "to": telefone_destino,
            "type": "text",
            "text": {"body": texto},
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(self._base_url, headers=self._headers, json=payload)
            if r.status_code >= 400:
                print("ERRO AO ENVIAR MENSAGEM:", r.status_code, r.text)
            r.raise_for_status()

    @staticmethod
    def normalizar_numero_brasileiro(telefone: str) -> str:
        """
        Corrige um problema conhecido com números de celular brasileiros:
        o campo 'from' recebido no webhook às vezes vem sem o '9' que os
        celulares no Brasil usam (formato: 55 + DDD + 8 dígitos), enquanto
        a API para ENVIAR mensagens espera o formato completo com o 9
        (55 + DDD + 9 dígitos). Sem essa correção, o envio falha com
        'Recipient phone number not in allowed list' mesmo quando o número
        está cadastrado corretamente, só que no formato com 9.

        Público porque também é usado pra COMPARAR dois números de telefone
        brasileiros (ex.: identificar se uma mensagem veio do advogado),
        já que os dois formatos podem representar a mesma pessoa.

        Só adiciona o 9 quando a parte local (8 dígitos) começa com 6-9,
        que é a faixa usada por celulares — telefones fixos (que começam
        com 2-5) têm o mesmo tamanho mas não devem ganhar o 9.
        """
        if telefone.startswith("55") and len(telefone) == 12:
            numero_local = telefone[4:]
            if numero_local[0] in "6789":
                ddd = telefone[2:4]
                return f"55{ddd}9{numero_local}"
        return telefone

    @staticmethod
    def extrair_mensagem_recebida(payload: dict) -> Optional[Tuple[str, str, str]]:
        """
        Extrai (telefone_remetente, texto, message_id) de um payload de
        webhook da Meta. Retorna None se não houver mensagem de texto de
        usuário (ex.: status de entrega/leitura ou outro tipo de evento).

        O message_id é usado para deduplicação: a Meta pode reenviar a
        mesma mensagem várias vezes se o webhook não responder rápido o
        suficiente, e sem controle disso o mesmo texto seria processado
        (e respondido) mais de uma vez.
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
            return msg["from"], msg["text"]["body"], msg["id"]
        except (KeyError, IndexError, TypeError):
            return None


# instância padrão usada pela aplicação
whatsapp_client = WhatsAppClient()