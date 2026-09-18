"""
Rotas HTTP do webhook do WhatsApp.

Camada: api — só sabe falar HTTP. Não contém regra de negócio: extrai o
payload, valida e delega tudo para `TriageService`. Trocar de canal (ex.:
adicionar um chat web) significa criar um novo router aqui que também chame
`triage_service.processar_turno`, sem duplicar lógica de negócio.
"""
from fastapi import APIRouter, Query, Request, Response

from ..core.config import settings
from ..integrations.whatsapp_client import whatsapp_client
from ..services.triage_service import triage_service

router = APIRouter()


@router.get("/webhook")
def verificar_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
):
    """Handshake exigido pela Meta ao configurar o webhook."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


@router.post("/webhook")
async def receber_mensagem(request: Request):
    print("\n========== POST /WEBHOOK RECEBIDO ==========")

    payload = await request.json()
    print("PAYLOAD:", payload)

    extraido = whatsapp_client.extrair_mensagem_recebida(payload)
    print("EXTRAIDO:", extraido)

    if extraido is None:
        # Pode ser um evento de status (entregue/lido) — apenas confirma recebimento.
        print("EVENTO IGNORADO")
        return {"status": "ignorado"}

    telefone, texto_usuario = extraido
    print(f"TELEFONE: {telefone}")
    print(f"MENSAGEM: {texto_usuario}")

    await triage_service.processar_turno(telefone, texto_usuario)
    return {"status": "ok"}