"""
Módulo `classificar_caso`: classifica área do direito, classe processual e
assunto (padrão descritivo, ver aviso em domain/classificacao_schemas.py),
e sugere qual template de petição já cadastrado se encaixa melhor.

Camada: services. O template_id sugerido só pode vir da lista real de
templates disponíveis — nunca inventado.
"""
import json
import logging

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.classificacao_schemas import ClassificarCasoRequest, RespostaClassificacao
from .peticao_service import peticao_service

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2


def _montar_system_prompt(templates_disponiveis: list) -> str:
    lista_templates = "\n".join(
        f"- {t['template_id']}: {t['titulo']} (área: {t['area']}, rito: {t['rito']})"
        for t in templates_disponiveis
    )
    return f"""
Você classifica um caso jurídico brasileiro a partir dos fatos fornecidos.

Determine:
1. area_direito: a área do direito (ex.: trabalhista, civel, familia, penal,
   consumidor, tributario, previdenciario, empresarial, imobiliario, outro).
2. classe_processual_sugerida: uma descrição da classe processual, no
   espírito da Tabela Processual Unificada do CNJ (ex.: "Procedimento Comum
   Cível", "Reclamação Trabalhista", "Ação de Alimentos"). Isto é uma
   aproximação descritiva, não o código oficial exato.
3. assunto_sugerido: o assunto principal, também no espírito do TPU (ex.:
   "Indenização por Dano Moral", "Rescisão Indireta", "Concessão de
   Benefício Previdenciário").
4. template_id_sugerido: escolha UM dos templates abaixo que melhor se
   encaixa no caso, ou null se nenhum se encaixar bem. NUNCA invente um
   template_id que não esteja nesta lista:
{lista_templates}

Regras:
- Não invente fatos que não foram fornecidos.
- Se os fatos forem insuficientes para uma classificação confiável, ainda
  assim dê sua melhor estimativa, mas mencione a incerteza na justificativa.
- Liste em "alternativas_consideradas" outras classificações plausíveis que
  você descartou, se houver ambiguidade real.

Responda SOMENTE com um JSON neste formato:
{{
  "area_direito": "...",
  "classe_processual_sugerida": "...",
  "assunto_sugerido": "...",
  "template_id_sugerido": "..." ou null,
  "justificativa": "...",
  "alternativas_consideradas": ["..."]
}}
"""


class ClassificacaoService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def classificar(self, entrada: ClassificarCasoRequest) -> RespostaClassificacao:
        templates_disponiveis = peticao_service.listar_templates()
        ids_validos = {t["template_id"] for t in templates_disponiveis}

        mensagens = [
            {"role": "system", "content": _montar_system_prompt(templates_disponiveis)},
            {"role": "user", "content": json.dumps(entrada.fatos, ensure_ascii=False)},
        ]

        ultimo_erro = None
        for tentativa in range(_MAX_TENTATIVAS):
            resp = self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=mensagens,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            texto = resp.choices[0].message.content or ""
            try:
                dados = json.loads(texto)
                # Salvaguarda determinística extra: mesmo que o prompt já
                # proíba, garantimos aqui que um template_id inventado nunca
                # passa disfarçado de sugestão válida.
                template_sugerido = dados.get("template_id_sugerido")
                if template_sugerido is not None and template_sugerido not in ids_validos:
                    logger.warning(
                        "Modelo sugeriu template_id inexistente '%s' — descartando.", template_sugerido
                    )
                    dados["template_id_sugerido"] = None
                return RespostaClassificacao(**dados)
            except (json.JSONDecodeError, ValidationError) as e:
                ultimo_erro = e
                logger.warning("Saída inválida de classificar_caso (tentativa %s): %s", tentativa + 1, e)
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )

        raise ValueError(f"Não foi possível classificar o caso após {_MAX_TENTATIVAS} tentativas: {ultimo_erro}")


# instância padrão usada pela aplicação
classificacao_service = ClassificacaoService()
