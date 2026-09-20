"""
Módulo `gerar_pecas_acessorias`: gera procuração, declaração de
hipossuficiência, notificação extrajudicial e rol de documentos —
documentos que acompanham a petição principal.

Camada: services. Reaproveita a mesma infraestrutura de gerar_peticao:
expansão determinística de blocos + preenchimento por IA com os mesmos
princípios de segurança (nunca inventar dado, marcar [PENDENTE] quando
faltar). Também reaproveita peca_repository — ou seja, uma peça acessória
gerada aqui já pode ser exportada em .docx/PDF pelo mesmo endpoint de
exportar_documento, sem nenhum código extra.
"""
import json
import logging
import uuid
from typing import Any, Dict

from openai import OpenAI
from pydantic import ValidationError

from ..core.config import settings
from ..domain.peca_acessoria_schemas import PecaAcessoriaRequest
from ..domain.peticao_schemas import Peca, PeticaoResponse
from ..repositories.peca_repository import peca_repository
from .peticao_service import _TEMPLATES_DATA, _expandir_blocos

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS = 2

_SYSTEM_PROMPT = """
Você preenche o ESQUELETO de um documento jurídico acessório brasileiro
(procuração, declaração, notificação extrajudicial ou rol de documentos)
com os dados fornecidos.

Regras invioláveis:
1. Nunca invente fato, valor, data, nome ou documento. Se um placeholder
   obrigatório (formato {{campo}}) não tiver dado correspondente, substitua
   por "[PENDENTE: <descrição breve do que falta>]".
2. Placeholders opcionais (formato {{?campo}} ou {{campo: sugestão}}) sem
   dado correspondente: use a sugestão entre chaves como valor padrão
   razoável, ou remova a cláusula se não fizer sentido sem ela.
3. Quando o esqueleto tiver uma instrução de repetição como
   "{{para_cada_X: 'formato da linha'}}", procure no campo "dados" uma
   lista correspondente (ex.: "documentos") e gere uma linha para cada
   item da lista, seguindo o formato indicado. Se a lista não foi
   fornecida ou está vazia, escreva "[PENDENTE: lista de itens]".
4. Preserve a estrutura e a linguagem formal do esqueleto.

Responda SOMENTE com um JSON neste formato, sem texto fora dele:
{
  "peca_texto": "o texto completo do documento, já preenchido",
  "campos_pendentes": ["lista curta dos campos que você marcou como PENDENTE"]
}
"""


class PecaAcessoriaService:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def listar_templates(self) -> list:
        return [
            {"template_id": t["template_id"], "titulo": t["titulo"]}
            for t in _TEMPLATES_DATA["pecas_acessorias"]
        ]

    def buscar_template(self, template_id: str) -> Dict[str, Any]:
        for template in _TEMPLATES_DATA["pecas_acessorias"]:
            if template["template_id"] == template_id:
                return template
        raise ValueError(f"Peça acessória '{template_id}' não encontrada.")

    async def gerar(self, entrada: PecaAcessoriaRequest) -> PeticaoResponse:
        template = self.buscar_template(entrada.template_id)
        esqueleto = _expandir_blocos(template["texto"], _TEMPLATES_DATA["blocos_reutilizaveis"])

        mensagens = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"ESQUELETO:\n{esqueleto}\n\n"
                    f"DADOS DISPONÍVEIS PARA PREENCHIMENTO:\n"
                    f"{json.dumps(entrada.dados, ensure_ascii=False)}"
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
                )
                peca_repository.salvar(peca)
                return PeticaoResponse(
                    peca_id=peca.peca_id,
                    template_id=peca.template_id,
                    titulo=peca.titulo,
                    peca_texto=peca.peca_texto,
                    campos_pendentes=peca.campos_pendentes,
                )
            except (json.JSONDecodeError, ValidationError, KeyError, TypeError) as e:
                ultimo_erro = e
                logger.warning(
                    "Saída inválida de gerar_pecas_acessorias (tentativa %s): %s", tentativa + 1, e
                )
                mensagens.append({"role": "assistant", "content": texto})
                mensagens.append(
                    {
                        "role": "user",
                        "content": f"JSON inválido ({e}). Responda de novo, SOMENTE com o JSON corrigido.",
                    }
                )

        raise ValueError(
            f"Não foi possível gerar a peça acessória após {_MAX_TENTATIVAS} tentativas: {ultimo_erro}"
        )


# instância padrão usada pela aplicação
peca_acessoria_service = PecaAcessoriaService()
