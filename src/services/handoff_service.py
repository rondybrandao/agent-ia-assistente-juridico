"""
Encaminhamento do resumo estruturado para o advogado/equipe responsável.

Camada: services. Hoje manda uma mensagem de WhatsApp direto pro advogado,
opcionalmente também para um webhook interno (Slack/Teams), e sempre loga em
arquivo como trilha de auditoria. Trocar por integração com um CRM jurídico é
só adicionar um método aqui, sem tocar em domain, api ou repositories.
"""
import json
import logging
from datetime import datetime

import httpx

from ..core.config import settings
from ..domain.schemas import SessaoConversa
from ..integrations.whatsapp_client import whatsapp_client

logger = logging.getLogger(__name__)


class HandoffService:
    def __init__(self, log_path: str = settings.HANDOFF_LOG_PATH) -> None:
        self._log_path = log_path

    def _montar_texto(self, sessao: SessaoConversa) -> str:
        r = sessao.resumo_atual
        linhas = [
            f"*Novo caso para triagem* — {settings.NOME_ESCRITORIO}",
            f"Telefone do cliente: {sessao.telefone}",
            f"Nome informado: {sessao.contato.nome or 'não informado'}",
            f"Área do direito: {r.area_direito.value}",
            f"Urgência: {r.urgencia.value.upper()}"
            + (f" — {r.motivo_urgencia}" if r.motivo_urgencia else ""),
            "",
            "Resumo do caso:",
            r.resumo_caso or "(sem resumo ainda)",
        ]
        if r.fatos_relevantes:
            linhas.append("\nFatos relevantes:")
            linhas += [f"- {f}" for f in r.fatos_relevantes]
        if r.documentos_mencionados:
            linhas.append("\nDocumentos mencionados:")
            linhas += [f"- {d}" for d in r.documentos_mencionados]
        if r.perguntas_em_aberto:
            linhas.append("\nPontos em aberto:")
            linhas += [f"- {p}" for p in r.perguntas_em_aberto]
        return "\n".join(linhas)

    async def encaminhar(self, sessao: SessaoConversa) -> None:
        texto = self._montar_texto(sessao)

        if settings.ADVOGADO_WHATSAPP_NUMERO:
            try:
                await whatsapp_client.enviar_mensagem_texto(
                    settings.ADVOGADO_WHATSAPP_NUMERO, texto
                )
            except Exception:
                # Falha ao notificar o advogado não pode derrubar a triagem do
                # cliente — o registro em log abaixo garante que o caso não
                # se perde, mesmo que o aviso em tempo real falhe.
                logger.exception(
                    "Falha ao enviar handoff por WhatsApp para o advogado (telefone cliente: %s)",
                    sessao.telefone,
                )

        if settings.WEBHOOK_INTERNO_HANDOFF:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(settings.WEBHOOK_INTERNO_HANDOFF, json={"text": texto})

        registro = {
            "timestamp": datetime.utcnow().isoformat(),
            "telefone": sessao.telefone,
            "resumo": sessao.resumo_atual.model_dump(),
        }
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


# instância padrão usada pela aplicação
handoff_service = HandoffService()