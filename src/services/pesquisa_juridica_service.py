"""
Chat de pesquisa jurídica para uso do advogado (não do cliente).

Camada: services. Diferente do llm_engine usado na triagem — que NUNCA pode
dar opinião jurídica — este serviço é uma ferramenta de trabalho para um
profissional do direito, então pode analisar os fatos e sugerir linhas de
ação jurídica. Também pode buscar informação atual na web (jurisprudência,
legislação, notícias) via function calling, quando o modelo julgar
necessário.
"""
import json
import logging
from typing import List

from openai import OpenAI

from ..core.config import settings
from ..domain.schemas import Mensagem, SessaoConversa
from ..integrations.web_search_client import web_search_client
from ..repositories.peca_repository import peca_repository

logger = logging.getLogger(__name__)

_MAX_ITERACOES_FERRAMENTA = 4

_FERRAMENTA_BUSCA_WEB = {
    "type": "function",
    "function": {
        "name": "buscar_na_web",
        "description": (
            "Busca informações atuais na internet: legislação, jurisprudência, "
            "notícias jurídicas. Use quando precisar de dados que podem ter "
            "mudado recentemente ou que você não tem certeza absoluta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termo de busca"},
            },
            "required": ["query"],
        },
    },
}


def _montar_system_prompt() -> str:
    return f"""
Você é um assistente de pesquisa jurídica de uso interno de {settings.NOME_ESCRITORIO},
para apoiar o trabalho do advogado responsável pelo caso.

Diferente de um assistente de atendimento ao público, aqui você PODE e DEVE:
- Analisar os fatos do caso e apontar possíveis linhas de ação jurídica.
- Sugerir fundamentos legais, teses e jurisprudência relevante.
- Ser direto, técnico e objetivo — está falando com um profissional do direito.

O contexto do caso (abaixo) inclui o estado atual de tudo que já foi
processado por outras ferramentas deste sistema: qualificação do autor,
fatos estruturados, competência definida, valor da causa calculado, prazo
calculado, estratégias geradas/escolhida, e a petição mais recente gerada
(com seus campos pendentes). Use isso para responder perguntas objetivas
sobre o andamento do caso, por exemplo:
- "Quais informações estão faltando para concluir a petição inicial?" →
  responda com a lista de "campos ainda pendentes" da petição mais recente
  E, se a qualificação do autor também estiver incompleta, inclua isso
  também (uma petição pendente às vezes reflete só a falta de qualificação).
- "Qual estratégia foi escolhida?", "Qual o valor da causa?", "Quando
  vence o prazo?" → responda diretamente com o que está no contexto.
- Se a informação pedida não estiver disponível no contexto (ex.: nenhuma
  petição foi gerada ainda, ou nenhum prazo foi calculado), diga isso
  claramente e sugira qual aba/ferramenta do sistema resolveria — não
  invente um dado que não está lá.

Use a ferramenta de busca na web quando precisar de informação atual
(mudanças legislativas recentes, jurisprudência, notícias). Sempre que usar
um resultado de busca, cite a fonte (nome do site ou publicação).

Suas respostas são um ponto de partida para a análise do advogado, que
mantém o julgamento profissional e a responsabilidade final pelo caso —
não repita esse aviso a cada resposta, apenas mantenha esse espírito no tom.

Responda em português do Brasil.
"""


def _montar_contexto_caso(sessao: SessaoConversa) -> str:
    r = sessao.resumo_atual
    linhas = [
        "=== CONTEXTO DO CASO ===",
        f"Cliente: {sessao.contato.nome or 'não informado'} ({sessao.telefone})",
        f"Área do direito: {r.area_direito.value}",
        f"Urgência: {r.urgencia.value}",
        f"Resumo: {r.resumo_caso or '(sem resumo)'}",
    ]
    if r.fatos_relevantes:
        linhas.append("Fatos relevantes: " + "; ".join(r.fatos_relevantes))
    if r.documentos_mencionados:
        linhas.append("Documentos mencionados: " + "; ".join(r.documentos_mencionados))

    dp = r.dados_pessoais_autor
    linhas.append("\n=== QUALIFICAÇÃO DO AUTOR ===")
    if dp.esta_completo():
        linhas.append(
            "Completa: nome, nacionalidade, estado civil, profissão, CPF, RG, "
            "endereço, CEP, cidade e data de nascimento já foram coletados."
        )
    else:
        linhas.append("INCOMPLETA. Campos ainda faltando: " + ", ".join(dp.campos_faltando()))

    if sessao.fatos_estruturados:
        fe = sessao.fatos_estruturados
        linhas.append("\n=== FATOS ESTRUTURADOS (extrair_fatos) ===")
        linhas.append(fe.resumo_narrativo)
        if fe.lacunas:
            linhas.append(
                "Lacunas identificadas: "
                + "; ".join(f"{l.dado_faltante} ({l.impacto})" for l in fe.lacunas)
            )

    if sessao.competencia_definida:
        c = sessao.competencia_definida
        linhas.append("\n=== COMPETÊNCIA DEFINIDA ===")
        linhas.append(
            f"{c.ramo_justica.value} / {c.rito.value}, foro: {c.foro_territorial}. "
            f"Dispensa advogado: {'sim' if c.dispensa_advogado else 'não'}."
        )

    if sessao.ultimo_calculo_valor_causa:
        vc = sessao.ultimo_calculo_valor_causa
        linhas.append("\n=== VALOR DA CAUSA CALCULADO ===")
        linhas.append(f"R$ {vc.valor_da_causa:.2f} (calculado em {vc.data_calculo}).")
        if vc.ha_correcao_monetaria_pendente:
            linhas.append(
                "Atenção: há correção monetária pendente de cálculo externo, "
                "não incluída neste valor."
            )

    if sessao.ultimo_prazo_calculado:
        p = sessao.ultimo_prazo_calculado
        linhas.append("\n=== PRAZO CALCULADO ===")
        linhas.append(f"Vencimento em {p.data_vencimento} ({p.fundamento_regime}).")

    if sessao.ultimas_estrategias:
        linhas.append("\n=== ESTRATÉGIAS GERADAS ===")
        for e in sessao.ultimas_estrategias.estrategias:
            marcador = (
                " [ESCOLHIDA]"
                if sessao.estrategia_escolhida and sessao.estrategia_escolhida.id == e.id
                else ""
            )
            linhas.append(f"- {e.id}: {e.nome}{marcador}")

    peca_recente = peca_repository.buscar_mais_recente_por_telefone(sessao.telefone)
    linhas.append("\n=== PETIÇÃO MAIS RECENTE GERADA PARA ESTE CASO ===")
    if peca_recente:
        linhas.append(f"Título: {peca_recente.titulo} (gerada em {peca_recente.criada_em}).")
        if peca_recente.campos_pendentes:
            linhas.append(
                "Campos ainda pendentes nesta peça: " + "; ".join(peca_recente.campos_pendentes)
            )
        else:
            linhas.append("Nenhum campo pendente sinalizado na última geração.")
    else:
        linhas.append("Nenhuma petição foi gerada ainda para este caso.")

    if sessao.historico:
        linhas.append("\n=== CONVERSA ORIGINAL COM O CLIENTE ===")
        for m in sessao.historico:
            linhas.append(f"{m.remetente}: {m.texto}")

    if sessao.anotacoes_advogado:
        linhas.append("\n=== ANOTAÇÕES DO ADVOGADO ===")
        for a in sessao.anotacoes_advogado:
            linhas.append(f"- {a.texto}")

    return "\n".join(linhas)


class PesquisaJuridicaService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    async def perguntar(self, sessao: SessaoConversa, pergunta_advogado: str) -> str:
        """
        Processa uma pergunta do advogado no chat de pesquisa, com acesso ao
        contexto do caso e à ferramenta de busca na web. Retorna a resposta
        final (já sem chamadas de ferramenta pendentes).
        """
        mensagens = [
            {"role": "system", "content": _montar_system_prompt()},
            {"role": "system", "content": _montar_contexto_caso(sessao)},
        ]
        for m in sessao.historico_pesquisa:
            role = "assistant" if m.remetente == "assistente_pesquisa" else "user"
            mensagens.append({"role": role, "content": m.texto})
        mensagens.append({"role": "user", "content": pergunta_advogado})

        resposta_final = await self._loop_com_ferramentas(mensagens)

        sessao.historico_pesquisa.append(Mensagem(remetente="advogado", texto=pergunta_advogado))
        sessao.historico_pesquisa.append(
            Mensagem(remetente="assistente_pesquisa", texto=resposta_final)
        )
        return resposta_final

    async def _loop_com_ferramentas(self, mensagens: List[dict]) -> str:
        for _ in range(_MAX_ITERACOES_FERRAMENTA):
            resp = self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=mensagens,
                tools=[_FERRAMENTA_BUSCA_WEB],
                tool_choice="auto",
                temperature=0.3,
            )
            msg = resp.choices[0].message

            if not msg.tool_calls:
                return (msg.content or "").strip()

            mensagens.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                }
            )

            for tool_call in msg.tool_calls:
                argumentos = json.loads(tool_call.function.arguments)
                query = argumentos.get("query", "")
                try:
                    resultados = await web_search_client.buscar(query)
                except Exception:
                    logger.exception("Falha ao buscar na web: %s", query)
                    resultados = []

                texto_resultado = self._formatar_resultados(resultados)
                mensagens.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": texto_resultado,
                    }
                )

        # Se estourou o limite de iterações sem resposta final, força uma
        # resposta simples com o que já foi conversado até aqui.
        return "Não consegui concluir a pesquisa a tempo. Tente reformular a pergunta."

    @staticmethod
    def _formatar_resultados(resultados: list) -> str:
        if not resultados:
            return "Nenhum resultado encontrado (ou busca na web não configurada)."
        linhas = []
        for r in resultados:
            linhas.append(f"- {r['titulo']} ({r['url']}): {r['conteudo'][:500]}")
        return "\n".join(linhas)


# instância padrão usada pela aplicação
pesquisa_juridica_service = PesquisaJuridicaService()