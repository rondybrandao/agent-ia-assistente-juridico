"""
Módulo `checar_pressupostos`: avalia prescrição/decadência, legitimidade,
interesse de agir, requerimento administrativo prévio e
litispendência/coisa julgada.

Camada: services. Diferente de definir_competencia, aqui não dá pra ser
100% determinístico — avaliar se uma pretensão está prescrita depende de
interpretar os fatos do caso. Por isso usamos IA, mas com instrução
explícita para nunca "confirmar" prescrição/decadência com certeza (isso é
questão jurídica sensível que o advogado deve sempre revisar) — o máximo
que o modelo faz é sinalizar risco.
"""
import json
import logging

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.pressupostos_schemas import (
    AvaliacaoPressuposto,
    CheckPressupostosRequest,
    RespostaPressupostos,
    StatusPressuposto,
)

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2

_SYSTEM_PROMPT = """
Você avalia pressupostos processuais preliminares de um caso jurídico
brasileiro, a partir dos fatos fornecidos. Avalie CADA um destes:

1. prescricao — há indício de que o prazo prescricional já passou?
2. decadencia — há indício de decadência de um direito potestativo?
3. legitimidade — as partes indicadas parecem ser as legítimas para a ação?
4. interesse_de_agir — há necessidade e utilidade em buscar o Judiciário?
5. requerimento_administrativo_previo — a matéria exige requerimento prévio
   (ex.: INSS) e, se sim, há indício de que foi feito?
6. litispendencia_ou_coisa_julgada — há indício de ação idêntica em curso
   ou já julgada?

Para cada um, defina status:
- "ok": não há indício de problema com base no que foi informado.
- "risco": há indício concreto de problema — explique o porquê.
- "lacuna": falta informação para avaliar esse pressuposto (diga qual dado
  falta em "dado_faltante").

Regras invioláveis:
1. NUNCA declare com certeza absoluta que algo está prescrito, decaído ou
   com outro problema definitivo — sempre enquadre como "risco" com a
   ressalva de que precisa de confirmação humana. Isso é análise jurídica
   sensível.
2. Não invente datas, valores ou fatos que não foram fornecidos — se
   faltar dado, marque "lacuna", não "ok" nem "risco".
3. Área do direito muda os prazos e regras aplicáveis (ex.: prescrição
   trabalhista é bienal/quinquenal, cível varia por matéria, previdenciário
   tem regra própria de requerimento administrativo) — considere isso.

Responda SOMENTE com um JSON no formato:
{"avaliacoes": [{"tipo": "prescricao|decadencia|legitimidade|interesse_de_agir|requerimento_administrativo_previo|litispendencia_ou_coisa_julgada", "status": "ok|risco|lacuna", "analise": "...", "dado_faltante": "..." ou null}]}

Inclua os 6 tipos listados acima, todos, na mesma ordem.
"""


class ChecarPressupostosService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def checar(self, entrada: CheckPressupostosRequest) -> RespostaPressupostos:
        entrada_usuario = (
            f"Área do direito: {entrada.area}\n"
            f"Data do último fato relevante: {entrada.data_ultimo_fato or 'não informada'}\n"
            f"Fatos: {json.dumps(entrada.fatos, ensure_ascii=False)}"
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
                avaliacoes = [AvaliacaoPressuposto(**item) for item in dados["avaliacoes"]]
                tem_risco = any(a.status == StatusPressuposto.RISCO for a in avaliacoes)
                return RespostaPressupostos(avaliacoes=avaliacoes, tem_risco_critico=tem_risco)
            except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as e:
                ultimo_erro = e
                logger.warning("Saída inválida de checar_pressupostos (tentativa %s): %s", tentativa + 1, e)
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )

        raise ValueError(
            f"Não foi possível checar pressupostos após {_MAX_TENTATIVAS} tentativas: {ultimo_erro}"
        )


# instância padrão usada pela aplicação
checar_pressupostos_service = ChecarPressupostosService()
