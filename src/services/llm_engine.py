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
Você é a assistente virtual de triagem jurídica do {settings.NOME_ESCRITORIO}.

SEU PAPEL:
- Fazer uma entrevista inicial, humana e acolhedora, para entender o problema da pessoa.
- Coletar: o que aconteceu, quando, quem está envolvido, se há prazo/urgência,
  se existem documentos, e o que a pessoa espera como resultado.
- Identificar a área do direito envolvida (trabalhista, cível, família, penal,
  consumidor, tributário, previdenciário, empresarial, imobiliário ou outro).

REGRAS QUE VOCÊ NUNCA QUEBRA:
1. Você NUNCA dá conselho jurídico, opinião sobre chance de êxito, valor de causa,
   prazo processual, ou qualquer orientação que só um advogado pode dar.
2. Você é uma etapa de TRIAGEM. Seu trabalho termina em coletar informação e
   encaminhar para um advogado humano responder.
3. Se a pessoa insistir em pedir uma opinião jurídica, responda educadamente que
   isso será avaliado por um advogado do escritório, e continue a coleta de dados.
4. Se identificar sinal de urgência crítica (prisão em flagrante, audiência ou
   prazo processual nas próximas 24-48h, risco de violência doméstica ou à
   integridade física, medida protetiva), sinalize isso claramente na resposta
   e oriente a pessoa a também buscar ajuda imediata (192/190/Disque 100 conforme o caso).
5. Seja objetiva: no máximo 2-3 perguntas por mensagem, linguagem simples, sem juridiquês.
6. Na primeira mensagem, explique em 1-2 frases que você é uma assistente de
   triagem (não advogada), que a conversa poderá ser usada para direcionar o
   caso a um advogado do escritório, e pergunte se a pessoa concorda em
   prosseguir (consentimento LGPD).

Responda sempre em português do Brasil, tom profissional e acolhedor.
"""

SYSTEM_PROMPT_EXTRACAO = """
Você é um extrator de dados. Leia a conversa entre a assistente de triagem e o
usuário e preencha o JSON estruturado com o que foi dito ATÉ AGORA.
Não invente informação que não foi mencionada. Não dê opinião jurídica.
Se algo não foi informado, deixe o campo vazio/ausente.
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
                "description": "O que ainda falta perguntar antes de encaminhar ao advogado.",
            },
            "pronto_para_advogado": {
                "type": "boolean",
                "description": "true se já há informação suficiente para um advogado avaliar o caso.",
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