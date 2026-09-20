"""
Módulo `revisar_peticao`: roda um checklist (art. 319/320 CPC, art. 840
CLT, ou os ritos especiais dos Juizados) sobre uma peça já gerada.

Camada: services. Importante: os textos legais abaixo são um resumo
didático dos requisitos, mantido estático no código — não são obtidos de
uma fonte oficial verificada em tempo real (isso dependeria do módulo
buscar_legislacao, que ainda não existe). Recomenda-se confirmar o texto
vigente periodicamente.

Este módulo NUNCA aprova uma peça para protocolo — ele só aponta o que
merece atenção. A decisão final é sempre do advogado.
"""
import json
import logging
from typing import Dict, List

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.revisao_schemas import (
    ChecklistDisponivel,
    ItemRevisao,
    RespostaRevisao,
    StatusItemChecklist,
)
from ..repositories.peca_repository import peca_repository

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2

# Resumo didático dos requisitos legais — ver aviso no docstring do módulo.
_CHECKLISTS: Dict[str, List[str]] = {
    "cpc_319": [
        "Endereçamento correto do juízo (art. 319, I, CPC)",
        "Qualificação completa das partes: nome, estado civil, profissão, CPF/CNPJ e endereço (art. 319, II, CPC)",
        "Fatos e fundamentos jurídicos do pedido, de forma coerente entre si (art. 319, III, CPC)",
        "Pedido certo e determinado, com suas especificações (art. 319, IV, CPC)",
        "Valor da causa compatível com os pedidos formulados (art. 319, V, CPC)",
        "Indicação das provas que a parte pretende produzir (art. 319, VI, CPC)",
        "Opção da parte pela realização (ou não) de audiência de conciliação/mediação (art. 319, VII, CPC)",
        "Menção aos documentos indispensáveis à propositura da ação (art. 320, CPC)",
    ],
    "clt_840": [
        "Nome e qualificação das partes: reclamante e reclamada (art. 840, §1º, CLT)",
        "Breve exposição dos fatos de que resulte o dissídio (art. 840, §1º, CLT)",
        "Pedido certo, determinado e com indicação de seu valor (art. 840, §1º, CLT)",
        "Data e indicação de assinatura do reclamante ou de quem o representa (art. 840, §1º, CLT)",
    ],
    "jec_lei_9099": [
        "Pedido formulado de forma simples e em linguagem acessível (art. 14, Lei 9.099/95)",
        "Valor da causa dentro do teto do Juizado Especial (40 salários mínimos)",
        "Se o valor ultrapassar 20 salários mínimos, indicação de advogado constituído",
        "Endereço correto das partes para citação/intimação",
    ],
    "jef_lei_10259": [
        "Comprovação (ou menção) do requerimento administrativo prévio, quando exigido pela matéria",
        "Valor da causa dentro do teto do Juizado Especial Federal (60 salários mínimos)",
        "Indicação de perícia ou provas técnicas específicas, quando a matéria exigir",
        "Endereço correto das partes e qualificação da autarquia/ente federal réu",
    ],
}

_SYSTEM_PROMPT = """
Você é um revisor de peças jurídicas. Recebe o texto de uma petição e uma
lista numerada de itens de um checklist legal. Para CADA item, avalie se
ele está:
- "ok": presente e adequado no texto.
- "faltando": ausente ou claramente incompleto.
- "atencao": presente, mas com algo que merece revisão humana cuidadosa
  (ex.: valor da causa parece incompatível com os pedidos, incoerência
  entre fatos e fundamentos, pedido vago).

Também verifique, independente do checklist:
- Se alguma citação de lei/súmula/precedente aparece no texto SEM estar na
  lista de "citacoes_utilizadas" fornecida — se isso acontecer, marque como
  item separado "Fidelidade das citações à lista verificada" com status
  "atencao" (nunca invente que uma citação existe: só reporte a partir do
  texto e da lista fornecidos).

Responda SOMENTE com um JSON no formato:
{"itens": [{"item": "texto do item do checklist", "status": "ok|faltando|atencao", "observacao": "..."}]}

Inclua todos os itens do checklist recebido, na mesma ordem, mais o item
extra de fidelidade de citações se aplicável.
"""


class RevisaoPeticaoService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    async def revisar(self, peca_id: str, checklist: ChecklistDisponivel) -> RespostaRevisao:
        peca = peca_repository.buscar(peca_id)
        if peca is None:
            raise ValueError(f"Peça '{peca_id}' não encontrada.")

        itens_checklist = _CHECKLISTS[checklist.value]

        # Checagem determinística (não depende do LLM): campos ainda
        # marcados como [PENDENTE] na peça. Mais confiável que pedir pro
        # modelo procurar isso sozinho.
        item_pendencias = ItemRevisao(
            item="Nenhum campo obrigatório ficou marcado como [PENDENTE]",
            status=StatusItemChecklist.OK if "[PENDENTE" not in peca.peca_texto else StatusItemChecklist.FALTANDO,
            observacao=(
                "Peça sem marcações pendentes."
                if "[PENDENTE" not in peca.peca_texto
                else "Ainda há campo(s) marcados como [PENDENTE] no texto — complete antes de prosseguir."
            ),
        )

        citacoes_utilizadas = [c.model_dump() for c in peca.citacoes_utilizadas]
        entrada_usuario = (
            f"CHECKLIST ({checklist.value}):\n"
            + "\n".join(f"{i+1}. {item}" for i, item in enumerate(itens_checklist))
            + f"\n\nTEXTO DA PEÇA:\n{peca.peca_texto}\n\n"
            f"CITAÇÕES UTILIZADAS (únicas permitidas):\n{json.dumps(citacoes_utilizadas, ensure_ascii=False)}"
        )

        mensagens = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": entrada_usuario},
        ]

        itens_llm: List[ItemRevisao] = []
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
                itens_llm = [ItemRevisao(**item) for item in dados["itens"]]
                break
            except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as e:
                ultimo_erro = e
                logger.warning("Saída inválida de revisar_peticao (tentativa %s): %s", tentativa + 1, e)
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )
        else:
            raise ValueError(
                f"Não foi possível revisar a peça após {_MAX_TENTATIVAS} tentativas: {ultimo_erro}"
            )

        itens_finais = [item_pendencias] + itens_llm
        tem_pendencia = any(i.status != StatusItemChecklist.OK for i in itens_finais)

        return RespostaRevisao(
            peca_id=peca_id,
            checklist_usado=checklist,
            itens=itens_finais,
            tem_pendencia=tem_pendencia,
        )


# instância padrão usada pela aplicação
revisao_peticao_service = RevisaoPeticaoService()
