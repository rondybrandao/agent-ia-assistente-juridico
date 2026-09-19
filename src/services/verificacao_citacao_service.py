"""
Módulo `verificar_citacao`: confirma, com base em busca na web (não no
"conhecimento" do modelo), se uma lei/súmula/precedente citado existe
mesmo, se o número e o órgão estão corretos, se o trecho citado confere
literalmente, e se não foi cancelado/superado.

Camada: services. Esta verificação é OBRIGATÓRIA antes de qualquer citação
entrar numa peça (ver prompt_estrategias.md e tools_juridico.json) — já
houve casos reais de advogados sancionados por citação inventada por IA.
"""
import json
import logging
from typing import List

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.citacao_schemas import (
    CitacaoEntrada,
    ResultadoVerificacaoCitacao,
    StatusVerificacao,
    TipoCitacao,
)
from ..integrations.web_search_client import web_search_client

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2

_SYSTEM_PROMPT = """
Você é um verificador de citações jurídicas. Sua única fonte de verdade são
os RESULTADOS DE BUSCA fornecidos abaixo — você NUNCA usa conhecimento
próprio para confirmar uma citação, mesmo que pareça familiar.

Analise a citação e decida um status:
- "confirmada": os resultados mostram claramente que a referência existe,
  com número/órgão batendo, está vigente, e o trecho citado (se houver)
  confere literalmente ou em substância com o texto encontrado.
- "divergente": os resultados mostram algo parecido, mas o número, o órgão,
  ou o trecho citado NÃO batem exatamente com o que foi buscado.
- "desatualizada": a referência existiu mas os resultados indicam que foi
  cancelada, revogada, superada ou revista.
- "nao_encontrada": nenhum resultado confirma a existência da referência.
- "inconclusiva": os resultados de busca não têm informação suficiente
  para decidir com segurança (nesse caso, NÃO marque como confirmada).

Regra de ouro: na dúvida, prefira "inconclusiva" ou "divergente" a
"confirmada". Um falso positivo aqui pode gerar uma petição com citação
inventada, o que já causou sanções reais a advogados.

Responda SOMENTE com um JSON neste formato, sem texto fora dele:
{
  "status": "confirmada | divergente | desatualizada | nao_encontrada | inconclusiva",
  "existe": true/false,
  "trecho_confere": true/false/null,
  "vigente": true/false/null,
  "fonte_url": "url do resultado mais relevante, ou null",
  "observacao": "explicação curta, citando o que os resultados mostraram"
}
"""


def _montar_query_busca(citacao: CitacaoEntrada) -> str:
    if citacao.tipo == TipoCitacao.SUMULA:
        return f"{citacao.referencia} texto oficial súmula"
    if citacao.tipo == TipoCitacao.ACORDAO:
        return f"{citacao.referencia} inteiro teor acórdão"
    if citacao.tipo == TipoCitacao.TEMA:
        return f"{citacao.referencia} tema repetitivo repercussão geral"
    # lei ou artigo
    return f"{citacao.referencia} texto vigente"


class VerificacaoCitacaoService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    async def verificar_uma(self, citacao: CitacaoEntrada) -> ResultadoVerificacaoCitacao:
        query = _montar_query_busca(citacao)
        try:
            resultados_busca = await web_search_client.buscar(query, max_resultados=5)
        except Exception:
            logger.exception("Falha ao buscar citação: %s", citacao.referencia)
            resultados_busca = []

        if not resultados_busca:
            # Sem busca configurada ou sem resultado nenhum: não dá pra
            # confirmar nada. Não vale a pena nem chamar o LLM aqui — a
            # resposta correta já é conhecida.
            return ResultadoVerificacaoCitacao(
                tipo=citacao.tipo,
                referencia=citacao.referencia,
                status=StatusVerificacao.INCONCLUSIVA,
                existe=False,
                observacao=(
                    "Nenhum resultado de busca disponível (verifique se TAVILY_API_KEY "
                    "está configurada ou tente novamente)."
                ),
            )

        evidencias = "\n\n".join(
            f"[{i+1}] {r['titulo']} ({r['url']})\n{r['conteudo'][:800]}"
            for i, r in enumerate(resultados_busca)
        )
        entrada_usuario = (
            f"Citação a verificar:\n"
            f"Tipo: {citacao.tipo.value}\n"
            f"Referência: {citacao.referencia}\n"
            f"Trecho citado: {citacao.trecho_citado or '(nenhum trecho fornecido)'}\n\n"
            f"Resultados de busca:\n{evidencias}"
        )

        mensagens = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": entrada_usuario},
        ]

        ultimo_erro = None
        for tentativa in range(_MAX_TENTATIVAS):
            resp = self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=mensagens,
                response_format={"type": "json_object"},
                temperature=0,
            )
            texto = resp.choices[0].message.content or ""
            try:
                dados = json.loads(texto)
                return ResultadoVerificacaoCitacao(
                    tipo=citacao.tipo,
                    referencia=citacao.referencia,
                    **dados,
                )
            except (json.JSONDecodeError, ValidationError) as e:
                ultimo_erro = e
                logger.warning(
                    "Saída inválida ao verificar '%s' (tentativa %s): %s",
                    citacao.referencia,
                    tentativa + 1,
                    e,
                )
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )

        # Se nem após retentativa deu certo, é mais seguro marcar como
        # inconclusiva do que arriscar confirmar algo sem validação real.
        return ResultadoVerificacaoCitacao(
            tipo=citacao.tipo,
            referencia=citacao.referencia,
            status=StatusVerificacao.INCONCLUSIVA,
            existe=False,
            observacao=f"Falha ao processar a verificação: {ultimo_erro}",
        )

    async def verificar(self, citacoes: List[CitacaoEntrada]) -> List[ResultadoVerificacaoCitacao]:
        return [await self.verificar_uma(c) for c in citacoes]


# instância padrão usada pela aplicação
verificacao_citacao_service = VerificacaoCitacaoService()
