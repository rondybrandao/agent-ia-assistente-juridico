"""
Interpreta comandos enviados pelo advogado via WhatsApp para consultar e
gerenciar os casos encaminhados pela triagem.

Camada: services. Mensagens vindas do número configurado em
ADVOGADO_WHATSAPP_NUMERO não passam pelo fluxo de triagem do cliente — são
tratadas aqui como comandos.

Comandos suportados:
    casos                          -> lista os casos pendentes
    ver <telefone>                 -> mostra o resumo completo de um caso
    anotar <telefone> <texto>      -> registra uma anotação no caso
    status <telefone> <status>     -> muda o status do caso
    ajuda                          -> mostra os comandos disponíveis
"""
import re
from typing import Optional

from ..domain.schemas import Anotacao, SessaoConversa, StatusCaso
from ..integrations.whatsapp_client import whatsapp_client
from ..repositories.session_repository import sessao_repository

_STATUS_VALIDOS = {status.value: status for status in StatusCaso}

_MENSAGEM_AJUDA = (
    "*Comandos disponíveis:*\n"
    "• casos — lista os casos pendentes\n"
    "• ver <telefone> — mostra o resumo completo de um caso\n"
    "• anotar <telefone> <texto> — registra uma anotação no caso\n"
    "• status <telefone> <novo_status> — muda o status do caso "
    f"({', '.join(_STATUS_VALIDOS.keys())})\n"
    "• ajuda — mostra esta mensagem"
)


class AdvogadoService:
    async def processar_comando(self, telefone_advogado: str, texto: str) -> None:
        resposta = self._interpretar(texto)
        await whatsapp_client.enviar_mensagem_texto(telefone_advogado, resposta)

    def _interpretar(self, texto: str) -> str:
        partes = texto.strip().split(maxsplit=2)
        comando = partes[0].lower() if partes else ""

        if comando in ("casos", "listar"):
            return self._listar_casos()
        if comando == "ver" and len(partes) >= 2:
            return self._ver_caso(partes[1])
        if comando == "anotar" and len(partes) >= 3:
            return self._anotar(partes[1], partes[2])
        if comando == "status" and len(partes) >= 3:
            return self._mudar_status(partes[1], partes[2])
        return _MENSAGEM_AJUDA

    @staticmethod
    def _somente_digitos(texto: str) -> str:
        return re.sub(r"\D", "", texto)

    def _encontrar_sessao(self, fragmento_telefone: str) -> Optional[SessaoConversa]:
        alvo = self._somente_digitos(fragmento_telefone)
        if not alvo:
            return None
        for sessao in sessao_repository.listar_todas():
            if sessao.telefone == alvo or sessao.telefone.endswith(alvo):
                return sessao
        return None

    def _listar_casos(self) -> str:
        casos = [
            s
            for s in sessao_repository.listar_todas()
            if s.status_caso in (StatusCaso.ENCAMINHADO, StatusCaso.EM_ANDAMENTO)
        ]
        if not casos:
            return "Nenhum caso pendente no momento."

        linhas = ["*Casos pendentes:*"]
        for s in casos:
            r = s.resumo_atual
            resumo_curto = (r.resumo_caso or "(sem resumo)")[:120]
            linhas.append(
                f"\n📞 {s.telefone}\n"
                f"Área: {r.area_direito.value} | Urgência: {r.urgencia.value} | "
                f"Status: {s.status_caso.value}\n"
                f"{resumo_curto}"
            )
        linhas.append("\nUse 'ver <telefone>' para ver os detalhes completos de um caso.")
        return "\n".join(linhas)

    def _ver_caso(self, fragmento_telefone: str) -> str:
        sessao = self._encontrar_sessao(fragmento_telefone)
        if sessao is None:
            return f"Nenhum caso encontrado com o telefone '{fragmento_telefone}'."

        r = sessao.resumo_atual
        linhas = [
            f"*Caso — {sessao.telefone}*",
            f"Nome: {sessao.contato.nome or 'não informado'}",
            f"Área: {r.area_direito.value} | Urgência: {r.urgencia.value} | "
            f"Status: {sessao.status_caso.value}",
            "",
            "Resumo:",
            r.resumo_caso or "(sem resumo)",
        ]
        if r.fatos_relevantes:
            linhas.append("\nFatos relevantes:")
            linhas += [f"- {f}" for f in r.fatos_relevantes]
        if r.documentos_mencionados:
            linhas.append("\nDocumentos mencionados:")
            linhas += [f"- {d}" for d in r.documentos_mencionados]
        if sessao.anotacoes_advogado:
            linhas.append("\nAnotações:")
            linhas += [
                f"- [{a.timestamp:%d/%m %H:%M}] {a.texto}" for a in sessao.anotacoes_advogado
            ]
        return "\n".join(linhas)

    def _anotar(self, fragmento_telefone: str, texto_anotacao: str) -> str:
        sessao = self._encontrar_sessao(fragmento_telefone)
        if sessao is None:
            return f"Nenhum caso encontrado com o telefone '{fragmento_telefone}'."

        sessao.anotacoes_advogado.append(Anotacao(texto=texto_anotacao))
        sessao_repository.salvar(sessao)
        return f"Anotação registrada no caso de {sessao.telefone}."

    def _mudar_status(self, fragmento_telefone: str, novo_status_texto: str) -> str:
        sessao = self._encontrar_sessao(fragmento_telefone)
        if sessao is None:
            return f"Nenhum caso encontrado com o telefone '{fragmento_telefone}'."

        novo_status_texto = novo_status_texto.strip().lower()
        if novo_status_texto not in _STATUS_VALIDOS:
            opcoes = ", ".join(_STATUS_VALIDOS.keys())
            return f"Status inválido. Use um destes: {opcoes}."

        sessao.status_caso = _STATUS_VALIDOS[novo_status_texto]
        sessao_repository.salvar(sessao)
        return f"Status do caso {sessao.telefone} atualizado para '{sessao.status_caso.value}'."


# instância padrão usada pela aplicação
advogado_service = AdvogadoService()
