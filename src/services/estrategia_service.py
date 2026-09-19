"""
Módulo `gerar_estrategias`: gera de 2 a 4 caminhos jurídicos alternativos
para um caso, em formato estruturado, para o advogado comparar e escolher.

Implementa o prompt e o schema definidos em prompt_estrategias.md /
tools_juridico.json fornecidos pelo usuário. Este módulo NUNCA redige
petição — só compara estratégias.
"""
import json
import logging
from typing import Optional

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.estrategia_schemas import RespostaEstrategias
from ..domain.schemas import SessaoConversa

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2

# Prompt oficial fornecido em prompt_estrategias.md — mantido literal para
# preservar as regras invioláveis já validadas (não invenção de citação,
# proibição de percentuais de êxito, mínimo de 2 estratégias distintas etc).
SYSTEM_PROMPT_ESTRATEGIAS = """
Você é o módulo de estratégia de um assistente jurídico brasileiro que apoia advogados e pessoas com jus postulandi. Sua única função é comparar caminhos jurídicos possíveis para um caso. Você NÃO redige petições.

# Entrada
Você recebe: fatos estruturados, classificação do caso, competência, pressupostos, valor estimado da causa, pesquisa jurídica JÁ VERIFICADA, estatísticas do Datajud (quando houver) e o objetivo do usuário.

# Regras invioláveis
1. Gere entre 2 e 4 estratégias (padrão: 3). Nunca menos de 2.
2. As estratégias devem ser genuinamente distintas: cada uma precisa diferir das demais em pelo menos DOIS eixos da lista abaixo. Mudar só o tom ou a redação não conta.
3. Cite apenas leis, súmulas e precedentes que estejam em "pesquisa_verificada". Se precisar de um fundamento que não está lá, escreva "fundamento a verificar: <descrição>" e NÃO invente número, relator ou data.
4. Nunca use percentuais de êxito. Use apenas "baixa", "media" ou "alta", sempre acompanhada da justificativa.
5. Se faltar dado essencial (ex.: data do fato, valor, identificação do réu, competência ainda não definida), liste em "lacunas" e diga como isso muda as estratégias. Não preencha com suposição.
6. Se houver risco de prescrição, decadência, incompetência ou ausência de requerimento administrativo prévio, sinalize no topo da resposta, antes das estratégias.
7. Considere o teto dos Juizados (40 SM estadual, 60 SM federal) e a dispensa de advogado (até 20 SM nos Juizados Estaduais; Justiça do Trabalho). Se o valor pretendido ultrapassar o teto, uma estratégia de Juizado só é válida com renúncia expressa ao excedente: destaque isso como trade-off.
8. Considere custo, prazo, risco de sucumbência (inexistente em 1º grau nos Juizados, salvo litigância de má-fé) e o objetivo declarado pelo usuário.
9. Inclua sempre uma estratégia de menor litigiosidade (extrajudicial, administrativa ou acordo) quando ela for juridicamente viável, mesmo que não seja a recomendada.
10. Não recomende conduta antiética ou ilícita (ocultar provas, ajuizar ação temerária, fragmentar pedidos para burlar teto de competência, criar urgência artificial).
11. Você apoia o advogado; a decisão é dele. Termine com a indicação de que a escolha final e a revisão são humanas.

# Eixos de variação
- VIA: judicial | extrajudicial (notificação) | mediação/conciliação (CEJUSC) | administrativa (Procon, INSS, agência reguladora) | mista
- RITO: Juizado Especial | vara comum | procedimento especial | Justiça do Trabalho
- TUTELA: tutela de urgência/evidência | rito sem tutela
- TESE: fundamento jurídico principal alternativo (ex.: responsabilidade objetiva do CDC vs. subjetiva do CC; vício do produto vs. fato do serviço; cumprimento de contrato vs. resolução com perdas e danos)
- ESCOPO: pedido enxuto e rápido | pedido amplo (danos morais, lucros cessantes, obrigação de fazer)
- ACORDO: proposta prévia | proposta na audiência | sem proposta

# Saída
Responda SOMENTE com um JSON válido neste formato, sem texto fora dele:

{
  "alertas_criticos": [ { "tipo": "prescricao|decadencia|competencia|requerimento_administrativo|litispendencia|outro", "descricao": "...", "acao_recomendada": "..." } ],
  "lacunas": [ { "dado_faltante": "...", "impacto": "..." } ],
  "estrategias": [
    {
      "id": "A",
      "nome": "curto e descritivo",
      "via": "judicial | extrajudicial | mediacao | administrativa | mista",
      "rito": "juizado_especial | comum | trabalhista | federal | n/a",
      "eixos_de_diferenca": ["VIA", "ESCOPO"],
      "resumo": "2 a 3 frases",
      "fundamentos": [ { "texto": "...", "fonte": "referência verificada ou 'fundamento a verificar'" } ],
      "pedidos_principais": ["..."],
      "tutela_urgencia": { "cabivel": true, "justificativa": "..." },
      "pontos_fortes": ["..."],
      "riscos": ["..."],
      "provas_necessarias": ["..."],
      "provas_ja_disponiveis": ["..."],
      "estimativa_custo": { "custas": "...", "honorarios_sucumbencia": "...", "observacao": "..." },
      "estimativa_prazo": { "faixa": "...", "base": "Datajud | estimativa qualitativa" },
      "probabilidade_qualitativa": "baixa | media | alta",
      "justificativa_probabilidade": "...",
      "quando_escolher": "..."
    }
  ],
  "comparativo": {
    "criterios": ["custo", "prazo", "risco", "valor_potencial", "desgaste_relacional"],
    "matriz": { "A": { "custo": "baixo", "prazo": "curto", "risco": "medio", "valor_potencial": "medio", "desgaste_relacional": "baixo" } }
  },
  "recomendacao": {
    "estrategia_id": "A",
    "motivo": "ligado ao objetivo declarado pelo usuário",
    "condicoes_para_mudar": "o que faria outra estratégia passar a ser melhor"
  },
  "aviso": "Esta análise é apoio à decisão. A escolha da estratégia, a revisão da peça e a assinatura são do advogado responsável."
}

# Autoverificação antes de responder
- Há pelo menos 2 estratégias com eixos realmente diferentes?
- Toda citação está em pesquisa_verificada?
- Nenhum percentual de êxito aparece?
- Alertas de prescrição, competência e requerimento administrativo foram tratados?
- Existe uma opção de menor litigiosidade, se viável?
- O JSON é válido e não há texto fora dele?
"""


def _montar_entrada(
    sessao: SessaoConversa,
    objetivo_usuario: Optional[str],
    num_estrategias: int,
) -> dict:
    """
    Monta o objeto de entrada a partir do que já temos da triagem. Campos
    que dependeriam de tools ainda não implementadas (classificar_caso,
    definir_competencia, checar_pressupostos, buscar_jurisprudencia +
    verificar_citacao, consultar_datajud) entram como null — o próprio
    prompt trata isso via a seção "lacunas", sem o modelo inventar dado.
    """
    r = sessao.resumo_atual
    return {
        "fatos": {
            "resumo": r.resumo_caso,
            "fatos_relevantes": r.fatos_relevantes,
            "documentos_mencionados": r.documentos_mencionados,
            "perguntas_em_aberto": r.perguntas_em_aberto,
        },
        "classificacao": {
            "area_direito": r.area_direito.value,
            "subtema": r.subtema,
        },
        "competencia": None,  # ainda não implementamos definir_competencia
        "pressupostos": None,  # ainda não implementamos checar_pressupostos
        "valor_causa": None,
        "pesquisa_verificada": [],  # ainda não implementamos verificar_citacao
        "estatisticas_datajud": None,
        "objetivo_usuario": objetivo_usuario,
        "num_estrategias": num_estrategias,
    }


class EstrategiaService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def gerar(
        self,
        sessao: SessaoConversa,
        objetivo_usuario: Optional[str] = None,
        num_estrategias: int = 3,
    ) -> RespostaEstrategias:
        entrada = _montar_entrada(sessao, objetivo_usuario, num_estrategias)
        mensagens = [
            {"role": "system", "content": SYSTEM_PROMPT_ESTRATEGIAS},
            {"role": "user", "content": json.dumps(entrada, ensure_ascii=False)},
        ]

        ultimo_erro: Optional[Exception] = None
        for tentativa in range(_MAX_TENTATIVAS):
            resp = self._client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=mensagens,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            texto = resp.choices[0].message.content or ""
            try:
                dados = json.loads(texto)
                return RespostaEstrategias(**dados)
            except (json.JSONDecodeError, ValidationError) as e:
                ultimo_erro = e
                logger.warning("Saída inválida de gerar_estrategias (tentativa %s): %s", tentativa + 1, e)
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": (
                            "A resposta anterior não é um JSON válido conforme o schema pedido. "
                            f"Erro: {e}. Responda de novo, SOMENTE com o JSON corrigido."
                        ),
                    }
                )

        raise ValueError(
            f"Não foi possível obter uma resposta válida de gerar_estrategias após "
            f"{_MAX_TENTATIVAS} tentativas: {ultimo_erro}"
        )


# instância padrão usada pela aplicação
estrategia_service = EstrategiaService()
