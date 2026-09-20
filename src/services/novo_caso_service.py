"""
Serviço de registro de novos casos via chat interno do advogado — a tela
inicial do Angular, para casos que NÃO vieram do WhatsApp/triagem.

Camada: services. Reaproveita a extração estruturada do llm_engine (mesma
lógica de "nunca inventar dado, marcar lacuna quando faltar"), mas usa um
prompt de conversa diferente: aqui quem está falando é o PRÓPRIO ADVOGADO
registrando um caso, não um cliente em triagem — então não faz sentido
pedir consentimento LGPD nem se apresentar como assistente de atendimento
ao público.

Como não vem de um número de WhatsApp real, o "telefone" da sessão vira um
identificador sintético ("manual-xxxxxxxxxx"), pra reaproveitar 100% da
infraestrutura já existente (repositório, listagem de casos, estratégias,
petição, ferramentas) sem precisar de nenhuma mudança estrutural nelas.
"""
import logging
import uuid
from typing import Optional, Tuple

from openai import OpenAI

from ..core.config import settings
from ..domain.schemas import DadosContato, Mensagem, SessaoConversa, StatusCaso
from ..repositories.session_repository import sessao_repository
from .llm_engine import llm_engine

logger = logging.getLogger(__name__)

_PREFIXO_CASO_MANUAL = "manual-"

_SYSTEM_PROMPT_NOVO_CASO = """
Você ajuda um advogado a registrar rapidamente um novo caso a partir da
descrição que ele digitar. Você está conversando com o PRÓPRIO ADVOGADO,
não com o cliente — não peça consentimento LGPD, não se apresente como
assistente de atendimento ao público, não trate a conversa como uma
triagem externa.

Faça perguntas objetivas (no máximo 1-2 por mensagem) só quando faltar
informação relevante para estruturar o caso: o que aconteceu, quem são as
partes, valores envolvidos, se há urgência, e a qualificação básica do
cliente (nome, CPF, endereço) se o advogado quiser deixar isso já
registrado. Seja direta e eficiente — o advogado já conhece o caso, você
só está ajudando a estruturar as informações.

Nunca dê conselho jurídico definitivo nesta conversa — se o advogado pedir
sua opinião sobre estratégia, sugira usar a aba de Estratégias, que tem
acesso a mais ferramentas (jurisprudência, legislação, pressupostos).

Responda em português do Brasil.
"""


def _gerar_id_caso_manual() -> str:
    return f"{_PREFIXO_CASO_MANUAL}{uuid.uuid4().hex[:10]}"


class NovoCasoService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def _gerar_resposta(self, historico: list) -> str:
        mensagens = [{"role": "system", "content": _SYSTEM_PROMPT_NOVO_CASO}]
        for m in historico:
            role = "assistant" if m.remetente == "assistente" else "user"
            mensagens.append({"role": role, "content": m.texto})

        resp = self._client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=mensagens,
            temperature=0.4,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()

    def processar_mensagem(self, case_id: Optional[str], mensagem: str) -> Tuple[str, SessaoConversa]:
        """
        Processa uma mensagem do advogado. Se case_id for None, cria um
        caso novo (gerando o identificador sintético). Retorna a resposta
        da IA e a sessão já atualizada e persistida.
        """
        if case_id is None:
            case_id = _gerar_id_caso_manual()
            sessao = SessaoConversa(
                telefone=case_id,
                contato=DadosContato(telefone=case_id),
                consentimento_lgpd=True,  # não se aplica: é o advogado falando, não o cliente
                encaminhada_advogado=True,
                status_caso=StatusCaso.ENCAMINHADO,
            )
        else:
            sessao = sessao_repository.carregar(case_id)
            if sessao is None:
                raise ValueError(f"Caso '{case_id}' não encontrado.")

        sessao.historico.append(Mensagem(remetente="usuario", texto=mensagem))

        resposta = self._gerar_resposta(sessao.historico)
        sessao.historico.append(Mensagem(remetente="assistente", texto=resposta))

        try:
            sessao.resumo_atual = llm_engine.extrair_resumo_estruturado(sessao.historico)
        except Exception:
            logger.exception("Falha ao extrair resumo estruturado do novo caso %s", case_id)

        sessao_repository.salvar(sessao)
        return resposta, sessao


# instância padrão usada pela aplicação
novo_caso_service = NovoCasoService()
