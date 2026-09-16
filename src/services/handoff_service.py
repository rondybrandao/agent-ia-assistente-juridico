"""
Encaminhamento do resumo estruturado para o advogado/equipe responsável.

Camada: services. Hoje envia para um webhook interno (Slack/Teams) e loga
em arquivo; trocar por integração com um CRM jurídico é só adicionar um
método aqui, sem tocar em domain, api ou repositories.
"""
import json
from datetime import datetime

import httpx

from ..core.config import settings
from ..domain.schemas import SessaoConversa


class HandoffService:
    def __init__(self, log_path: str = "handoffs.log.jsonl") -> None:
        self._log_path = log_path

    def _montar_texto(self, sessao: SessaoConversa) -> str:
        r = sessao.resumo_atual
        linhas = [
            f"*Novo caso para triagem* — {settings.NOME_ESCRITORIO}",
            f"Telefone: {sessao.telefone}",
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