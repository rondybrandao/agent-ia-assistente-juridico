"""
Módulo `buscar_legislacao`: busca dispositivos legais em fontes oficiais
(Planalto, LexML, normas estaduais) e extrai candidatos de citação
estruturados.

Camada: services. Espelha jurisprudencia_service.py de propósito — mesma
lógica de "buscar depois extrair candidatos, nunca confirmar aqui". Todo
candidato retornado ainda precisa passar por verificar_citacao antes de
virar fundamento aceito numa peça ou estratégia.

Diferença em relação à busca de jurisprudência: aqui NÃO restringimos por
domínio (Tavily include_domains), porque "normas estaduais" pode estar
publicada em qualquer diário oficial estadual — restringir a só
planalto.gov.br/lexml.gov.br perderia esses casos. Em vez disso, o nome
dessas fontes entra como termo de busca, funcionando como uma dica, não uma
regra rígida.
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

_SYSTEM_PROMPT_EXTRACAO = """
Você extrai candidatos de citação de dispositivos legais (leis, artigos,
decretos, normas estaduais) a partir de resultados de busca. Sua única
fonte são os resultados fornecidos — NUNCA invente número de lei, número
de artigo ou texto que não apareça literalmente no material.

Regras:
1. Se não conseguir identificar com clareza a referência exata (ex.: "Lei
   8.078/1990, art. 42"), NÃO a inclua — é melhor devolver menos candidatos
   do que arriscar uma referência errada.
2. "referencia" deve ser a identificação formal (ex.: "Lei 8.078/1990, art.
   42", "CPC art. 319", "CF art. 5º, XXXV").
3. "trecho_citado" deve trazer o texto vigente do dispositivo, se estiver
   claro nos resultados — inclusive alertando se os resultados indicarem
   que o dispositivo foi revogado ou alterado recentemente (inclua essa
   informação dentro do próprio trecho_citado, já que não há campo
   separado para isso).
4. Use "tipo": "lei" para a lei/norma em geral, ou "artigo" quando a busca
   for sobre um artigo específico.

Responda SOMENTE com um JSON no formato:
{"citacoes": [{"tipo": "lei|artigo", "referencia": "...", "trecho_citado": "..." ou null}]}
"""


def _montar_query(consulta: str, norma: Optional[str], dispositivo: Optional[str]) -> str:
    partes = [consulta]
    if norma:
        partes.append(norma)
    if dispositivo:
        partes.append(dispositivo)
    partes.append("texto da lei vigente Planalto LexML")
    return " ".join(partes)


class LegislacaoService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    async def buscar(
        self,
        consulta: str,
        norma: Optional[str] = None,
        dispositivo: Optional[str] = None,
        limite: int = 5,
    ) -> List[CitacaoEntrada]:
        """
        Busca dispositivos legais relacionados à consulta e extrai
        candidatos de citação. O retorno são CANDIDATOS — ainda não
        verificados (ver verificacao_citacao_service.py).
        """
        query = _montar_query(consulta, norma, dispositivo)

        try:
            resultados_busca = await web_search_client.buscar(query, max_resultados=limite)
        except Exception:
            logger.exception("Falha ao buscar legislação: %s", query)
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
            logger.warning("Falha ao extrair candidatos de legislação: %s", e)
            return []


# instância padrão usada pela aplicação
legislacao_service = LegislacaoService()
