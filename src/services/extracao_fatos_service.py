"""
Módulo `extrair_fatos`: transforma o relato livre do usuário numa linha do
tempo estruturada (fatos, partes, valores, pontos controvertidos).

Camada: services. Regra central: NUNCA inferir dado que não foi dito
explicitamente — datas incertas ficam como texto aproximado, dado ausente
vira "lacuna", nunca um valor inventado.

Limitação atual: o parâmetro documentos_ids referencia documentos que
seriam processados por ler_documentos (OCR), que ainda não existe neste
projeto. Quando informado, isso é sinalizado ao modelo apenas como
contexto — o conteúdo desses documentos não está disponível, então
qualquer fato que dependesse deles vira lacuna.
"""
import json
import logging

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.fatos_schemas import ExtrairFatosRequest, RespostaExtracaoFatos
from ..domain.schemas import SessaoConversa
from ..repositories.session_repository import sessao_repository

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2


def montar_relato_da_sessao(sessao: SessaoConversa) -> str:
    """
    Constrói o texto de 'relato' a partir do histórico de triagem — só as
    mensagens do usuário, já que são elas que representam fatos alegados;
    as perguntas da assistente não são fato nenhum e atrapalhariam a
    extração se entrassem junto.
    """
    linhas = [m.texto for m in sessao.historico if m.remetente == "usuario"]
    return "\n".join(linhas)

_SYSTEM_PROMPT = """
Você extrai fatos de um relato jurídico e organiza numa linha do tempo
estruturada, junto com as partes envolvidas, valores mencionados e pontos
controvertidos.

Regras invioláveis:
1. NUNCA infira ou invente um fato, data, nome, valor ou documento que não
   tenha sido dito explicitamente no relato.
2. Se uma data não foi dada com precisão, preencha "data" como null e
   registre a expressão original em "data_aproximada_texto" (ex.: "início
   de 2024", "há uns 3 meses") — nunca converta uma data aproximada numa
   data exata inventada.
3. Se uma parte (nome, qualificação) não foi identificada claramente,
   deixe o campo como null. Se isso for relevante para o caso, registre em
   "lacunas".
4. "pontos_controvertidos" são pontos do relato que parecem contraditórios,
   incompletos, ou que dependem da versão da outra parte para ficarem
   claros — não são uma opinião jurídica sobre o mérito.
5. Se "documentos_ids" foi informado mas você não recebeu o conteúdo
   desses documentos, não invente o que eles diriam — registre em
   "lacunas" que o conteúdo desses documentos ainda precisa ser
   incorporado.
6. "resumo_narrativo" é um resumo objetivo em prosa, de 2 a 4 frases,
   só com o que foi dito.

Responda SOMENTE com um JSON neste formato:
{
  "resumo_narrativo": "...",
  "linha_do_tempo": [{"data": "AAAA-MM-DD" ou null, "data_aproximada_texto": "..." ou null, "descricao": "...", "fonte": "relato" ou um id de documento}],
  "partes": [{"papel": "...", "nome": "..." ou null, "qualificacao": "..." ou null}],
  "valores_mencionados": [{"descricao": "...", "valor": 0.0 ou null, "moeda": "BRL", "data_referencia": "..." ou null}],
  "pontos_controvertidos": [{"descricao": "...", "motivo": "..."}],
  "lacunas": [{"dado_faltante": "...", "impacto": "..."}]
}
"""


class ExtracaoFatosService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def extrair(self, entrada: ExtrairFatosRequest) -> RespostaExtracaoFatos:
        entrada_usuario = f"Relato:\n{entrada.relato}"
        if entrada.documentos_ids:
            entrada_usuario += (
                f"\n\nIDs de documentos referenciados (conteúdo NÃO disponível "
                f"nesta chamada): {', '.join(entrada.documentos_ids)}"
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
                temperature=0.1,
            )
            texto = resp.choices[0].message.content or ""
            try:
                dados = json.loads(texto)
                return RespostaExtracaoFatos(**dados)
            except (json.JSONDecodeError, ValidationError) as e:
                ultimo_erro = e
                logger.warning("Saída inválida de extrair_fatos (tentativa %s): %s", tentativa + 1, e)
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )

        raise ValueError(f"Não foi possível extrair os fatos após {_MAX_TENTATIVAS} tentativas: {ultimo_erro}")

    def extrair_e_persistir(self, sessao: SessaoConversa) -> RespostaExtracaoFatos:
        """
        Usada quando a extração precisa alimentar o pipeline (estratégias,
        pressupostos etc.) — constrói o relato a partir da própria sessão,
        extrai, salva o resultado na sessão e persiste no banco.
        """
        relato = montar_relato_da_sessao(sessao)
        resultado = self.extrair(ExtrairFatosRequest(relato=relato))
        sessao.fatos_estruturados = resultado
        sessao_repository.salvar(sessao)
        return resultado


# instância padrão usada pela aplicação
extracao_fatos_service = ExtracaoFatosService()