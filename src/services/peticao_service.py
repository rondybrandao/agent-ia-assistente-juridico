"""
Módulo `gerar_peticao`: monta o esqueleto da peça de forma determinística
(expandindo os blocos reutilizáveis em Python puro, sem IA) e só então usa
o modelo para preencher os dados factuais nos placeholders restantes.

Por que dividir assim: expandir "{{bloco:fecho}}" ou "{{bloco:gratuidade}}"
é uma substituição de texto fixa — não tem por que arriscar a IA reescrever
isso à toa. A IA entra só na parte que exige julgamento (encaixar fatos e
valores nos campos), e mesmo aí só pode usar dados fornecidos.
"""
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.peticao_schemas import Peca, PeticaoRequest, PeticaoResponse
from ..repositories.peca_repository import peca_repository
from ..repositories.session_repository import sessao_repository

logger = logging.getLogger(__name__)

_CAMINHO_TEMPLATES = Path(__file__).resolve().parent.parent / "data" / "templates_peticoes.json"
_MAX_TENTATIVAS = 2

_PADRAO_BLOCO = re.compile(r"\{\{bloco:(\w+)\}\}")

_SYSTEM_PROMPT = """
Você preenche o ESQUELETO de uma petição jurídica brasileira. O esqueleto já
tem toda a estrutura fixa — sua tarefa é diferente para dois tipos de
placeholder que aparecem nele:

TIPO 1 — DADOS FACTUAIS (nome, CPF, RG, endereço, datas, valores, nomes de
partes, números de documento etc.): você NUNCA inventa. Se um placeholder
obrigatório (formato {{campo}}) desse tipo não tiver dado correspondente
fornecido, substitua-o exatamente por "[PENDENTE: <descrição breve do que
falta>]". Placeholders opcionais (formato {{?campo}}) sem dado
correspondente: remova a frase/cláusula relacionada, sem deixar buraco
estranho no texto.

TIPO 2 — FUNDAMENTAÇÃO JURÍDICA E PEDIDOS (qualquer placeholder dentro de
uma seção "DO DIREITO", "DOS PEDIDOS", ou cujo nome comece com
"fundamentacao_" ou "pedido_"): isso NÃO é um dado que falta — é um trecho
que VOCÊ REDIGE, como um advogado redigiria. Escreva 2-5 frases de
argumentação jurídica conectando os FATOS deste caso específico à base
legal:
  - Se o próprio texto do esqueleto já cita um artigo/lei ao lado do
    placeholder (ex.: "Da inversão do ônus da prova (CDC art. 6º, VIII):
    {{fundamentacao_inversao}}"), essa citação já está aprovada — REDIJA o
    argumento aplicando-a aos fatos do caso. Você não está inventando uma
    citação nova, só explicando por que ela se aplica aqui.
  - Se precisar de uma citação que NÃO está no esqueleto, use apenas o que
    estiver em "citacoes_verificadas". Nunca cite lei, súmula ou precedente
    fora do que já está no esqueleto ou em "citacoes_verificadas".
  - Só use "[PENDENTE: ...]" num placeholder de fundamentação/pedido na
    situação rara em que ele exigir uma citação nova indispensável que não
    está disponível em nenhum dos dois lugares acima — nesse caso, ainda
    assim tente redigir o argumento e marque só a citação faltante, ex.:
    "..., conforme entendimento consolidado [PENDENTE: citação específica a
    verificar]." Nunca deixe o placeholder inteiro como PENDENTE só porque
    "não veio um dado pronto" — fundamentação é para você escrever.
  - Use "estrategia_escolhida" (quando presente) como guia: os
    "fundamentos" dela são uma ótima fonte para essas seções; os
    "pedidos_principais" dela guiam a seção de pedidos.

Regras invioláveis (valem para os dois tipos):
1. Preserve a estrutura, a ordem das seções e a linguagem jurídica formal
   do esqueleto. Não resuma nem corte seções.
2. Você pode redigir a narrativa de "dos fatos" em prosa jurídica coerente,
   mas SOMENTE com base nos fatos fornecidos — sem adicionar detalhes que
   não foram informados.
3. Nunca invente fato, valor, data, nome ou documento (tipo 1). Nunca cite
   lei/súmula/precedente fora do esqueleto ou de "citacoes_verificadas"
   (tipo 2).

Responda SOMENTE com um JSON neste formato, sem texto fora dele:
{
  "peca_texto": "o texto completo da peça, já preenchida",
  "campos_pendentes": ["lista curta dos campos que você marcou como PENDENTE"]
}
"""


def _carregar_templates() -> Dict[str, Any]:
    with open(_CAMINHO_TEMPLATES, encoding="utf-8") as f:
        return json.load(f)


_TEMPLATES_DATA = _carregar_templates()


def _expandir_blocos(texto: str, blocos: Dict[str, str], profundidade: int = 3) -> str:
    """Substitui {{bloco:nome}} pelo texto do bloco correspondente. Repete
    algumas vezes para o caso (não observado nos templates atuais, mas
    possível) de um bloco referenciar outro bloco."""
    for _ in range(profundidade):
        nova = _PADRAO_BLOCO.sub(lambda m: blocos.get(m.group(1), m.group(0)), texto)
        if nova == texto:
            break
        texto = nova
    return texto


def _resolver_blocos_condicionais(
    blocos_base: Dict[str, str], entrada: PeticaoRequest
) -> Dict[str, str]:
    """
    Alguns templates referenciam nomes de bloco 'conceituais' que dependem
    de uma decisão sobre o caso (tem advogado? autor é PF ou PJ? pede
    gratuidade?) — não existem literalmente em blocos_reutilizaveis.
    Resolve essas escolhas aqui, em código determinístico, em vez de
    deixar a IA decidir por conta própria.
    """
    blocos = dict(blocos_base)

    possui_advogado = entrada.partes.get("possui_advogado", True)
    blocos["fecho_ou_fecho_sem_advogado"] = (
        blocos_base["fecho"] if possui_advogado else blocos_base["fecho_sem_advogado"]
    )

    pede_gratuidade = bool(entrada.partes.get("pede_gratuidade") or entrada.fatos.get("pede_gratuidade"))
    blocos["gratuidade_se_aplicavel"] = blocos_base["gratuidade"] if pede_gratuidade else ""

    autor_tipo = entrada.partes.get("autor_tipo", "pessoa_fisica")
    blocos["qualificacao_pf_ou_pj_autor"] = (
        blocos_base["qualificacao_pj"] if autor_tipo == "pessoa_juridica" else blocos_base["qualificacao_pf"]
    )

    return blocos


def _montar_esqueleto(template: Dict[str, Any], blocos: Dict[str, str]) -> str:
    partes_texto = []
    for secao in template["secoes"]:
        texto_expandido = _expandir_blocos(secao["texto"], blocos)
        partes_texto.append(texto_expandido)
    return "\n\n".join(partes_texto)


class PeticaoService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def buscar_template(self, template_id: str) -> Dict[str, Any]:
        for template in _TEMPLATES_DATA["templates"]:
            if template["template_id"] == template_id:
                return template
        raise ValueError(f"Template '{template_id}' não encontrado.")

    def listar_templates(self) -> list:
        """Usado pelo frontend/WhatsApp para mostrar quais templates existem."""
        return [
            {"template_id": t["template_id"], "titulo": t["titulo"], "area": t["area"], "rito": t["rito"]}
            for t in _TEMPLATES_DATA["templates"]
        ]

    async def gerar(self, entrada: PeticaoRequest) -> PeticaoResponse:
        template = self.buscar_template(entrada.template_id)
        blocos_resolvidos = _resolver_blocos_condicionais(_TEMPLATES_DATA["blocos_reutilizaveis"], entrada)
        esqueleto = _montar_esqueleto(template, blocos_resolvidos)

        estrategia_escolhida = entrada.estrategia_escolhida
        if entrada.telefone and not estrategia_escolhida:
            sessao = sessao_repository.carregar(entrada.telefone)
            if sessao and sessao.estrategia_escolhida:
                estrategia_escolhida = sessao.estrategia_escolhida.model_dump()

        dados_preenchimento = {
            "fatos": entrada.fatos,
            "partes": entrada.partes,
            "competencia": entrada.competencia,
            "valor_causa": entrada.valor_causa,
            "estrategia_escolhida": estrategia_escolhida,
            "citacoes_verificadas": [c.model_dump() for c in entrada.citacoes_verificadas],
            "pedidos_adicionais": entrada.pedidos_adicionais,
        }

        mensagens = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"ESQUELETO DA PEÇA:\n{esqueleto}\n\n"
                    f"DADOS DISPONÍVEIS PARA PREENCHIMENTO:\n"
                    f"{json.dumps(dados_preenchimento, ensure_ascii=False)}"
                ),
            },
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
                peca = Peca(
                    peca_id=str(uuid.uuid4()),
                    template_id=entrada.template_id,
                    titulo=template["titulo"],
                    peca_texto=dados["peca_texto"],
                    campos_pendentes=dados.get("campos_pendentes", []),
                    citacoes_utilizadas=entrada.citacoes_verificadas,
                )
                peca_repository.salvar(peca)
                return PeticaoResponse(
                    peca_id=peca.peca_id,
                    template_id=peca.template_id,
                    titulo=peca.titulo,
                    peca_texto=peca.peca_texto,
                    campos_pendentes=peca.campos_pendentes,
                )
            except (json.JSONDecodeError, ValidationError, KeyError) as e:
                ultimo_erro = e
                logger.warning("Saída inválida de gerar_peticao (tentativa %s): %s", tentativa + 1, e)
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )

        raise ValueError(
            f"Não foi possível gerar a petição após {_MAX_TENTATIVAS} tentativas: {ultimo_erro}"
        )


# instância padrão usada pela aplicação
peticao_service = PeticaoService()