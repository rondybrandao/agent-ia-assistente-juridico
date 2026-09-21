"""
Módulo `gerar_estrategias`: gera de 2 a 4 caminhos jurídicos alternativos
para um caso, em formato estruturado, para o advogado comparar e escolher.

Implementa o prompt e o schema definidos em prompt_estrategias.md /
tools_juridico.json fornecidos pelo usuário. Este módulo NUNCA redige
petição — só compara estratégias.
"""
import json
import logging
from typing import List, Optional

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.citacao_schemas import CitacaoEntrada, StatusVerificacao
from ..domain.competencia_schemas import RespostaCompetencia
from ..domain.estrategia_schemas import RespostaEstrategias
from ..domain.pressupostos_schemas import CheckPressupostosRequest, RespostaPressupostos
from ..domain.schemas import SessaoConversa
from ..repositories.session_repository import sessao_repository
from .jurisprudencia_service import jurisprudencia_service
from .legislacao_service import legislacao_service
from .pressupostos_service import checar_pressupostos_service
from .verificacao_citacao_service import verificacao_citacao_service

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

# Nota adicional (fora do prompt original): quando a entrada trouxer o campo
# "citacoes_verificadas_mas_nao_confirmadas", essas referências passaram por
# checagem e NÃO puderam ser confirmadas — a regra 3 acima já proíbe citá-las
# como fundamento; se forem relevantes, use "fundamento a verificar: <descrição>".
_NOTA_CITACOES_NAO_CONFIRMADAS = (
    "Nota adicional: se a entrada trouxer 'citacoes_verificadas_mas_nao_confirmadas', "
    "essas referências passaram por verificação e NÃO puderam ser confirmadas. "
    "Você não pode citá-las como fundamento — se forem relevantes, use "
    "'fundamento a verificar: <descrição>', conforme a regra 3."
)


def _montar_entrada(
    sessao: SessaoConversa,
    objetivo_usuario: Optional[str],
    num_estrategias: int,
    citacoes_confirmadas: list,
    citacoes_rejeitadas: list,
    competencia: Optional[RespostaCompetencia],
    pressupostos: Optional[RespostaPressupostos],
) -> dict:
    """
    Monta o objeto de entrada a partir do que já temos da triagem. Campos
    que dependeriam de tools ainda não implementadas (consultar_datajud)
    entram como null — o próprio prompt trata isso via a seção "lacunas",
    sem o modelo inventar dado.

    `pesquisa_verificada` só recebe citações que passaram por
    verificar_citacao com status CONFIRMADA — nunca citações não checadas.
    """
    r = sessao.resumo_atual
    entrada = {
        "fatos": sessao.construir_fatos_dict(),
        "classificacao": {
            "area_direito": r.area_direito.value,
            "subtema": r.subtema,
        },
        "competencia": competencia.model_dump() if competencia else None,
        "pressupostos": pressupostos.model_dump() if pressupostos else None,
        "valor_causa": None,
        "pesquisa_verificada": citacoes_confirmadas,
        "estatisticas_datajud": None,
        "objetivo_usuario": objetivo_usuario,
        "num_estrategias": num_estrategias,
    }
    if citacoes_rejeitadas:
        entrada["citacoes_verificadas_mas_nao_confirmadas"] = citacoes_rejeitadas
    return entrada


class EstrategiaService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    async def gerar(
        self,
        sessao: SessaoConversa,
        objetivo_usuario: Optional[str] = None,
        num_estrategias: int = 3,
        citacoes_candidatas: Optional[List[CitacaoEntrada]] = None,
        buscar_jurisprudencia_automaticamente: bool = False,
        buscar_legislacao_automaticamente: bool = False,
        competencia: Optional[RespostaCompetencia] = None,
        pressupostos: Optional[RespostaPressupostos] = None,
        checar_pressupostos_automaticamente: bool = False,
    ) -> RespostaEstrategias:
        if not citacoes_candidatas and (
            buscar_jurisprudencia_automaticamente or buscar_legislacao_automaticamente
        ):
            consulta = sessao.resumo_atual.resumo_caso or sessao.resumo_atual.area_direito.value
            citacoes_candidatas = []
            if buscar_jurisprudencia_automaticamente:
                try:
                    citacoes_candidatas += await jurisprudencia_service.buscar(consulta)
                except Exception:
                    logger.exception(
                        "Falha na busca automática de jurisprudência para o caso %s", sessao.telefone
                    )
            if buscar_legislacao_automaticamente:
                try:
                    citacoes_candidatas += await legislacao_service.buscar(consulta)
                except Exception:
                    logger.exception(
                        "Falha na busca automática de legislação para o caso %s", sessao.telefone
                    )

        if checar_pressupostos_automaticamente and pressupostos is None:
            try:
                pressupostos = checar_pressupostos_service.checar(
                    CheckPressupostosRequest(
                        area=sessao.resumo_atual.area_direito.value,
                        fatos=sessao.construir_fatos_dict(),
                    )
                )
            except Exception:
                logger.exception("Falha na checagem automática de pressupostos para o caso %s", sessao.telefone)
                pressupostos = None

        citacoes_confirmadas: list = []
        citacoes_rejeitadas: list = []

        if citacoes_candidatas:
            resultados = await verificacao_citacao_service.verificar(citacoes_candidatas)
            for res in resultados:
                item = {
                    "tipo": res.tipo.value,
                    "referencia": res.referencia,
                    "fonte_url": res.fonte_url,
                    "trecho_confere": res.trecho_confere,
                    "observacao": res.observacao,
                }
                if res.status == StatusVerificacao.CONFIRMADA:
                    citacoes_confirmadas.append(item)
                else:
                    citacoes_rejeitadas.append({**item, "status": res.status.value})

        entrada = _montar_entrada(
            sessao,
            objetivo_usuario,
            num_estrategias,
            citacoes_confirmadas,
            citacoes_rejeitadas,
            competencia,
            pressupostos,
        )
        system_prompt = SYSTEM_PROMPT_ESTRATEGIAS
        if citacoes_rejeitadas:
            system_prompt = f"{SYSTEM_PROMPT_ESTRATEGIAS}\n\n{_NOTA_CITACOES_NAO_CONFIRMADAS}"

        mensagens = [
            {"role": "system", "content": system_prompt},
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
                resultado = RespostaEstrategias(**dados)
                # Persiste pra permitir que o advogado "escolha" uma delas
                # depois (ver EstrategiaService.escolher) — sem isso, o
                # endpoint de escolha não teria como saber quais IDs existem.
                sessao.ultimas_estrategias = resultado
                sessao_repository.salvar(sessao)
                return resultado
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

    def escolher(self, sessao: SessaoConversa, estrategia_id: str):
        """
        O advogado escolhe uma das estratégias já geradas para o caso. A
        escolha fica salva na sessão e passa a guiar o restante do
        processo — em especial, gerar_peticao usa isso automaticamente
        quando chamado com o telefone deste caso.
        """
        if sessao.ultimas_estrategias is None:
            raise ValueError("Nenhuma estratégia foi gerada ainda para este caso.")

        escolhida = next(
            (e for e in sessao.ultimas_estrategias.estrategias if e.id == estrategia_id), None
        )
        if escolhida is None:
            ids_disponiveis = [e.id for e in sessao.ultimas_estrategias.estrategias]
            raise ValueError(
                f"Estratégia '{estrategia_id}' não encontrada. IDs disponíveis: {ids_disponiveis}"
            )

        sessao.estrategia_escolhida = escolhida
        sessao_repository.salvar(sessao)
        return escolhida


# instância padrão usada pela aplicação
estrategia_service = EstrategiaService()