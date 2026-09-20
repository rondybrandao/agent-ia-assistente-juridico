"""
Orquestração do fluxo de triagem: liga domain + repositories + LLM + handoff.

Camada: services — é aqui que fica a regra "o que acontece a cada mensagem
recebida", independente de o canal ser WhatsApp, um chat web, etc. A camada
`api` só chama `processar_turno`; toda a lógica de negócio mora aqui.
"""
import logging

from ..core.config import settings
from ..domain.schemas import Mensagem, SessaoConversa, StatusCaso, Urgencia
from ..integrations.whatsapp_client import whatsapp_client
from ..repositories.session_repository import sessao_repository
from .advogado_service import advogado_service
from .handoff_service import handoff_service
from .llm_engine import llm_engine

logger = logging.getLogger(__name__)

_CONFIRMACOES_POSITIVAS = {"sim", "concordo", "ok", "pode", "aceito", "claro"}


def _eh_confirmacao_positiva(texto: str) -> bool:
    texto_lower = texto.strip().lower()
    return any(p in texto_lower for p in _CONFIRMACOES_POSITIVAS)


class TriageService:
    """Caso de uso principal: processar uma mensagem recebida de um usuário."""

    async def processar_turno(self, telefone: str, texto_usuario: str) -> None:
        if self._eh_mensagem_do_advogado(telefone):
            await advogado_service.processar_comando(telefone, texto_usuario)
            return

        sessao = sessao_repository.obter_ou_criar(telefone)

        if sessao.encerrada:
            await whatsapp_client.enviar_mensagem_texto(
                telefone,
                "Seu atendimento já foi encaminhado. "
                "Em breve alguém da equipe entrará em contato.",
            )
            return

        sessao.historico.append(Mensagem(remetente="usuario", texto=texto_usuario))

        # Consentimento LGPD é pré-requisito para seguir com a triagem.
        if not sessao.consentimento_lgpd:
            if _eh_confirmacao_positiva(texto_usuario) and len(sessao.historico) > 1:
                sessao.consentimento_lgpd = True
            else:
                await self._responder_e_salvar(sessao, texto_usuario)
                return

        await self._responder_e_salvar(sessao, texto_usuario)
        self._atualizar_resumo(sessao)
        sessao_repository.salvar(sessao)

        if self._deve_encaminhar(sessao):
            await self._encerrar_com_handoff(sessao)

    def _eh_mensagem_do_advogado(self, telefone: str) -> bool:
        if not settings.ADVOGADO_WHATSAPP_NUMERO:
            return False
        return whatsapp_client.normalizar_numero_brasileiro(
            telefone
        ) == whatsapp_client.normalizar_numero_brasileiro(settings.ADVOGADO_WHATSAPP_NUMERO)

    async def _responder_e_salvar(self, sessao: SessaoConversa, texto_usuario: str) -> None:
        resposta = llm_engine.gerar_resposta_conversa(sessao.historico[:-1], texto_usuario)
        sessao.historico.append(Mensagem(remetente="assistente", texto=resposta))
        sessao_repository.salvar(sessao)
        await whatsapp_client.enviar_mensagem_texto(sessao.telefone, resposta)

    def _atualizar_resumo(self, sessao: SessaoConversa) -> None:
        sessao.resumo_atual = llm_engine.extrair_resumo_estruturado(sessao.historico)

    def _deve_encaminhar(self, sessao: SessaoConversa) -> bool:
        resumo = sessao.resumo_atual

        # Urgência crítica sempre encaminha na hora, mesmo com qualificação
        # incompleta — não faz sentido segurar um caso de risco esperando CEP.
        if resumo.urgencia == Urgencia.CRITICA:
            return True

        # Trava determinística: não confiamos só na IA dizer que "está
        # pronto" — exigimos de verdade que os 10 dados de qualificação
        # estejam preenchidos antes de liberar o encaminhamento.
        return resumo.pronto_para_advogado and resumo.dados_pessoais_autor.esta_completo()

    async def _encerrar_com_handoff(self, sessao: SessaoConversa) -> None:
        await handoff_service.encaminhar(sessao)
        sessao.encaminhada_advogado = True
        sessao.encerrada = True
        sessao.status_caso = StatusCaso.ENCAMINHADO
        sessao_repository.salvar(sessao)
        await whatsapp_client.enviar_mensagem_texto(
            sessao.telefone,
            "Obrigada pelas informações! Já encaminhei seu caso para "
            f"{settings.NOME_ESCRITORIO}. Em breve alguém da equipe entrará "
            "em contato por aqui.",
        )
        logger.info("Sessão %s encaminhada ao advogado.", sessao.telefone)


# instância padrão usada pela aplicação
triage_service = TriageService()