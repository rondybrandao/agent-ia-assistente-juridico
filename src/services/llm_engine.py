"""
Motor de IA da triagem jurídica.

Camada: services — regra de negócio de "como conversar" e "como extrair
dados", isolada da forma como a mensagem chega (WhatsApp, web chat, etc.)
e de como é persistida.

Duas responsabilidades separadas de propósito:
1. gerar_resposta_conversa   -> conduz a entrevista, nunca dá conselho jurídico.
2. extrair_resumo_estruturado -> gera o ResumoTriagem (JSON) que vai ao advogado.
"""
import json
from typing import List

from openai import OpenAI

from ..core.config import settings
from ..domain.schemas import Mensagem, ResumoTriagem

SYSTEM_PROMPT_CONVERSA = f"""
Você é a assistente virtual de triagem jurídica de {settings.NOME_ESCRITORIO}.

SEU PAPEL:
- Fazer uma entrevista inicial, humana e acolhedora, para entender o problema da pessoa.
- Coletar: o que aconteceu, quando, quem está envolvido, se há prazo/urgência,
  se existem documentos, e o que a pessoa espera como resultado.
- Identificar a área do direito envolvida (trabalhista, cível, família, penal,
  consumidor, tributário, previdenciário, empresarial, imobiliário ou outro).
- Coletar a QUALIFICAÇÃO COMPLETA da pessoa (necessária para qualquer petição):
  nome completo, nacionalidade, estado civil, profissão, CPF, RG, endereço
  completo, CEP, cidade e data de nascimento. Peça isso aos poucos, 1-2 dados
  por vez, misturado naturalmente com as perguntas sobre o caso — não despeje
  a lista inteira de uma vez, e não deixe de perguntar o que ainda falta.

REGRAS QUE VOCÊ NUNCA QUEBRA:
1. Você NUNCA dá conselho jurídico, opinião sobre chance de êxito, valor de causa,
   prazo processual, ou qualquer orientação que só {settings.NOME_ESCRITORIO} pode dar.
2. Você é uma etapa de TRIAGEM. Seu trabalho termina em coletar informação e
   encaminhar para {settings.NOME_ESCRITORIO} responder.
3. Se a pessoa insistir em pedir uma opinião jurídica, responda educadamente que
   isso será avaliado por {settings.NOME_ESCRITORIO}, e continue a coleta de dados.
4. Se identificar sinal de urgência crítica (prisão em flagrante, audiência ou
   prazo processual nas próximas 24-48h, risco de violência doméstica ou à
   integridade física, medida protetiva), sinalize isso claramente na resposta
   e oriente a pessoa a também buscar ajuda imediata (192/190/Disque 100 conforme o caso).
   Nesse caso, o encaminhamento urgente NÃO espera a qualificação completa.
5. Seja objetiva: no máximo 2-3 perguntas por mensagem, linguagem simples, sem juridiquês.
6. Na primeira mensagem, explique em 1-2 frases que você é uma assistente de
   triagem (não advogada), que a conversa poderá ser usada para direcionar o
   caso a {settings.NOME_ESCRITORIO}, e pergunte se a pessoa concorda em
   prosseguir (consentimento LGPD).
7. NUNCA invente nomes de pessoas, advogados, cargos ou informações que não
   estejam explicitamente fornecidas a você. Use somente "{settings.NOME_ESCRITORIO}"
   para se referir a quem vai avaliar o caso — nunca crie um nome diferente.
8. NÃO considere a triagem concluída (não diga que vai encaminhar, não pare de
   perguntar) enquanto qualquer um dos 10 dados de qualificação do item acima
   ainda não tiver sido informado — exceto em caso de urgência crítica (regra 4).

Responda sempre em português do Brasil, tom profissional e acolhedor.
"""

SYSTEM_PROMPT_EXTRACAO = """
Você é um extrator de dados. Leia a conversa entre a assistente de triagem e o
usuário e preencha o JSON estruturado com o que foi dito ATÉ AGORA.
Não invente informação que não foi mencionada. Não dê opinião jurídica.
Se algo não foi informado, deixe o campo vazio/ausente.

"pronto_para_advogado" só pode ser true se:
(a) os fatos do caso já dão pra entender o que aconteceu, E
(b) TODOS os 10 campos de "dados_pessoais_autor" estão preenchidos
    (nome, nacionalidade, estado_civil, profissao, cpf, rg,
    endereco_completo, cep, cidade, data_nascimento),
EXCETO quando "urgencia" for "critica" — nesse caso, marque
pronto_para_advogado true mesmo com qualificação incompleta, e liste os
dados pessoais que faltam em "perguntas_em_aberto".
Se pronto_para_advogado for false por falta de dado pessoal, liste
explicitamente cada campo faltante em "perguntas_em_aberto" (ex.: "CPF do
autor", "endereço completo do autor").
"""

_EXTRACAO_SCHEMA = {
    "name": "resumo_triagem",
    "description": "Resumo estruturado do caso jurídico relatado até agora, para uso do advogado.",
    "parameters": {
        "type": "object",
        "properties": {
            "area_direito": {
                "type": "string",
                "enum": [
                    "trabalhista", "civel", "familia", "penal", "consumidor",
                    "tributario", "previdenciario", "empresarial", "imobiliario",
                    "outro", "indefinido",
                ],
            },
            "subtema": {"type": "string"},
            "resumo_caso": {"type": "string", "description": "Resumo objetivo dos fatos, 3-6 frases."},
            "urgencia": {"type": "string", "enum": ["baixa", "media", "alta", "critica"]},
            "motivo_urgencia": {"type": "string"},
            "fatos_relevantes": {"type": "array", "items": {"type": "string"}},
            "documentos_mencionados": {"type": "array", "items": {"type": "string"}},
            "perguntas_em_aberto": {
                "type": "array",
                "items": {"type": "string"},
                "description": "O que ainda falta perguntar antes de encaminhar ao advogado, incluindo dados pessoais faltantes.",
            },
            "dados_pessoais_autor": {
                "type": "object",
                "description": "Qualificação civil do autor. Deixe um campo ausente/null se não foi informado — nunca invente.",
                "properties": {
                    "nome": {"type": "string"},
                    "nacionalidade": {"type": "string"},
                    "estado_civil": {"type": "string"},
                    "profissao": {"type": "string"},
                    "cpf": {"type": "string"},
                    "rg": {"type": "string"},
                    "endereco_completo": {"type": "string"},
                    "cep": {"type": "string"},
                    "cidade": {"type": "string"},
                    "data_nascimento": {"type": "string"},
                },
            },
            "pronto_para_advogado": {
                "type": "boolean",
                "description": "true somente se os fatos E toda a qualificação pessoal foram coletados (ou a urgência é crítica).",
            },
        },
        "required": ["area_direito", "urgencia", "pronto_para_advogado"],
    },
}


class LLMEngine:
    """Encapsula toda a interação com o provedor de LLM."""

    def __init__(self) -> None:
        self._client = OpenAI(api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL)

    def gerar_resposta_conversa(self, historico: List[Mensagem], mensagem_usuario: str) -> str:
        mensagens = [{"role": "system", "content": SYSTEM_PROMPT_CONVERSA}]
        for m in historico:
            role = "assistant" if m.remetente == "assistente" else "user"
            mensagens.append({"role": role, "content": m.texto})
        mensagens.append({"role": "user", "content": mensagem_usuario})

        resp = self._client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=mensagens,
            temperature=0.4,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()

    def extrair_resumo_estruturado(self, historico: List[Mensagem]) -> ResumoTriagem:
        transcricao = "\n".join(f"{m.remetente}: {m.texto}" for m in historico)

        resp = self._client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_EXTRACAO},
                {"role": "user", "content": transcricao},
            ],
            tools=[{"type": "function", "function": _EXTRACAO_SCHEMA}],
            tool_choice={"type": "function", "function": {"name": "resumo_triagem"}},
            temperature=0,
        )
        tool_call = resp.choices[0].message.tool_calls[0]
        dados = json.loads(tool_call.function.arguments)
        return ResumoTriagem(**dados)


# instância padrão usada pela aplicação
llm_engine = LLMEngine()