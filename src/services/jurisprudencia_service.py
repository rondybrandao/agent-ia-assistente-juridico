"""
Módulo `buscar_jurisprudencia`: busca jurisprudência, súmulas e temas
repetitivos em tribunais e extrai candidatos de citação estruturados.

Camada: services. Importante: esta busca NUNCA produz citações prontas pra
usar em peça — ela só gera CANDIDATOS. Todo candidato tem que passar por
verificar_citacao antes de virar fundamento aceito (ver
verificacao_citacao_service.py e o uso em estrategia_service.py).
"""
import json
import logging
from typing import List, Optional

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.citacao_schemas import CitacaoEntrada, CitacoesExtraidas
from ..integrations.web_search_client import web_search_client

logger = logging.getLogger(__name__)

# Mapeamento best-effort de tribunal -> domínio oficial, usado para
# restringir a busca. Quando o tribunal não está no mapa, a busca segue sem
# restrição de domínio (o nome do tribunal ainda entra no texto da busca).
_DOMINIOS_POR_TRIBUNAL = {
    "TJAM": "tjam.jus.br",
    "TRF1": "trf1.jus.br",
    "TRT11": "trt11.jus.br",
    "STJ": "stj.jus.br",
    "STF": "stf.jus.br",
    "TST": "tst.jus.br",
}

_SYSTEM_PROMPT_EXTRACAO = """
Você extrai candidatos de citação jurídica (leis, súmulas, acórdãos, temas
repetitivos) a partir de resultados de busca. Sua única fonte são os
resultados fornecidos — NUNCA invente um número, relator, data ou tribunal
que não apareça literalmente no texto.

Regras:
1. Se não conseguir identificar com clareza o número/referência exata de um
   precedente, NÃO o inclua — é melhor devolver menos candidatos do que
   arriscar um número errado.
2. "referencia" deve ser a identificação formal (ex.: "REsp 1.234.567/SP",
   "Súmula 297 STJ", "Tema 1.016 STJ").
3. "trecho_citado" é opcional: só preencha se houver um trecho relevante
   claramente atribuível àquele precedente no texto fornecido.
4. Cada candidato aqui ainda será verificado numa etapa separada — seu papel
   é só identificar candidatos plausíveis, não confirmar que estão corretos.

Responda SOMENTE com um JSON no formato:
{"citacoes": [{"tipo": "lei|artigo|sumula|acordao|tema", "referencia": "...", "trecho_citado": "..." ou null}]}
"""


def _montar_query(consulta: str, tribunais: Optional[List[str]], tipo: Optional[List[str]]) -> str:
    partes = [consulta]
    if tribunais:
        partes.append(" ".join(tribunais))
    if tipo:
        partes.append(" ".join(tipo))
    return " ".join(partes)


class JurisprudenciaService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    async def buscar(
        self,
        consulta: str,
        tribunais: Optional[List[str]] = None,
        tipo: Optional[List[str]] = None,
        limite: int = 10,
    ) -> List[CitacaoEntrada]:
        """
        Busca jurisprudência relacionada à consulta e extrai candidatos de
        citação. O retorno são CANDIDATOS — ainda não verificados.
        """
        query = _montar_query(consulta, tribunais, tipo)
        include_domains = None
        if tribunais:
            include_domains = [
                _DOMINIOS_POR_TRIBUNAL[t] for t in tribunais if t in _DOMINIOS_POR_TRIBUNAL
            ] or None

        try:
            resultados_busca = await web_search_client.buscar(
                query, max_resultados=limite, include_domains=include_domains
            )
        except Exception:
            logger.exception("Falha ao buscar jurisprudência: %s", query)
            return []

        if not resultados_busca:
            return []

        evidencias = "\n\n".join(
            f"[{i+1}] {r['titulo']} ({r['url']})\n{r['conteudo'][:800]}"
            for i, r in enumerate(resultados_busca)
        )

        resp = self._client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_EXTRACAO},
                {"role": "user", "content": f"Consulta original: {consulta}\n\nResultados de busca:\n{evidencias}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        texto = resp.choices[0].message.content or ""
        try:
            dados = json.loads(texto)
            return CitacoesExtraidas(**dados).citacoes
        except (json.JSONDecodeError, ValidationError) as e:
            logger.warning("Falha ao extrair candidatos de jurisprudência: %s", e)
            return []


# instância padrão usada pela aplicação
jurisprudencia_service = JurisprudenciaService()
