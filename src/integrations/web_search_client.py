"""
Cliente para a API de busca da Tavily, usada pelo chat de pesquisa jurídica
do advogado para buscar jurisprudência, legislação e notícias atuais.

Camada: integrations — isola a dependência externa. Trocar de provedor de
busca (ex.: SerpAPI, Bing) significa reescrever só este arquivo.
"""
from typing import List, Optional, TypedDict

import httpx

from ..core.config import settings

_BASE_URL = "https://api.tavily.com/search"


class ResultadoBusca(TypedDict):
    titulo: str
    url: str
    conteudo: str


class WebSearchClient:
    async def buscar(
        self,
        query: str,
        max_resultados: int = 5,
        include_domains: Optional[List[str]] = None,
    ) -> List[ResultadoBusca]:
        """Busca na web e retorna uma lista de resultados resumidos.

        `include_domains` restringe a busca a domínios específicos (ex.:
        sites de tribunais), quando informado.
        """
        if not settings.TAVILY_API_KEY:
            return []

        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "max_results": max_resultados,
            "search_depth": "advanced",
        }
        if include_domains:
            payload["include_domains"] = include_domains

        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(_BASE_URL, json=payload)
            r.raise_for_status()
            dados = r.json()

        return [
            ResultadoBusca(
                titulo=item.get("title", ""),
                url=item.get("url", ""),
                conteudo=item.get("content", ""),
            )
            for item in dados.get("results", [])
        ]


# instância padrão usada pela aplicação
web_search_client = WebSearchClient()