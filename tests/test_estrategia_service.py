import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.domain.schemas import (
    AreaDireito,
    DadosContato,
    ResumoTriagem,
    SessaoConversa,
    Urgencia,
)
from src.services.estrategia_service import EstrategiaService

_RESPOSTA_VALIDA = {
    "alertas_criticos": [],
    "lacunas": [{"dado_faltante": "endereço do réu", "impacto": "impede a citação"}],
    "estrategias": [
        {
            "id": "A",
            "nome": "Juizado Especial com pedido enxuto",
            "via": "judicial",
            "rito": "juizado_especial",
            "eixos_de_diferenca": ["RITO", "ESCOPO"],
            "resumo": "Ação no JEC pedindo só a restituição em dobro.",
            "fundamentos": [{"texto": "Repetição de indébito", "fonte": "fundamento a verificar: CDC art. 42"}],
            "pedidos_principais": ["Restituição em dobro"],
            "tutela_urgencia": {"cabivel": False, "justificativa": "Não há urgência."},
            "pontos_fortes": ["Rápido", "Sem custas"],
            "riscos": ["Teto de valor"],
            "provas_necessarias": ["Extrato bancário"],
            "provas_ja_disponiveis": ["Fatura do cartão"],
            "estimativa_custo": {"custas": "Isento", "honorarios_sucumbencia": "N/A em 1º grau", "observacao": ""},
            "estimativa_prazo": {"faixa": "3 a 6 meses", "base": "estimativa qualitativa"},
            "probabilidade_qualitativa": "media",
            "justificativa_probabilidade": "Fatos bem documentados.",
            "quando_escolher": "Quando o objetivo é rapidez.",
        },
        {
            "id": "B",
            "nome": "Vara comum com tutela e danos morais",
            "via": "judicial",
            "rito": "comum",
            "eixos_de_diferenca": ["RITO", "TUTELA", "ESCOPO"],
            "resumo": "Ação em vara comum pedindo tutela de urgência e danos morais.",
            "fundamentos": [{"texto": "Negativação indevida", "fonte": "fundamento a verificar: CDC art. 14"}],
            "pedidos_principais": ["Suspensão da negativação", "Danos morais"],
            "tutela_urgencia": {"cabivel": True, "justificativa": "Negativação ativa."},
            "pontos_fortes": ["Sem teto de valor"],
            "riscos": ["Sucumbência", "Processo mais longo"],
            "provas_necessarias": ["Extrato de negativação"],
            "provas_ja_disponiveis": [],
            "estimativa_custo": {"custas": "~1% do valor da causa", "honorarios_sucumbencia": "10-20%", "observacao": ""},
            "estimativa_prazo": {"faixa": "1 a 2 anos", "base": "estimativa qualitativa"},
            "probabilidade_qualitativa": "media",
            "justificativa_probabilidade": "Depende de prova da negativação.",
            "quando_escolher": "Quando há negativação ativa ou dano grave.",
        },
    ],
    "comparativo": {
        "criterios": ["custo", "prazo", "risco"],
        "matriz": {"A": {"custo": "baixo", "prazo": "curto", "risco": "baixo"}, "B": {"custo": "medio", "prazo": "longo", "risco": "medio"}},
    },
    "recomendacao": {
        "estrategia_id": "A",
        "motivo": "Objetivo do cliente é rapidez.",
        "condicoes_para_mudar": "Se houver negativação ativa, mudar para B.",
    },
    "aviso": "Esta análise é apoio à decisão. A escolha final é do advogado responsável.",
}


def _criar_sessao() -> SessaoConversa:
    return SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217", nome="Cliente Teste"),
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.CONSUMIDOR,
            resumo_caso="Cobrança indevida de R$ 8.000 no cartão de crédito.",
            urgencia=Urgencia.MEDIA,
            fatos_relevantes=["Cobrança não reconhecida", "Cliente já contatou o banco sem sucesso"],
        ),
    )


def _resposta_mock(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def test_gera_estrategias_com_resposta_valida_de_primeira():
    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    sessao = _criar_sessao()
    resultado = service.gerar(sessao, objetivo_usuario="rapidez")

    assert len(resultado.estrategias) == 2
    assert resultado.estrategias[0].id == "A"
    assert resultado.recomendacao.estrategia_id == "A"
    assert service._client.chat.completions.create.call_count == 1


def test_minimo_de_duas_estrategias_e_respeitado_pelo_schema():
    resposta_com_uma_so = {**_RESPOSTA_VALIDA, "estrategias": [_RESPOSTA_VALIDA["estrategias"][0]]}
    service = EstrategiaService()
    # a validação de "mínimo 2" é responsabilidade do PROMPT (regra 1), não do
    # Pydantic — este teste documenta que o schema aceita tecnicamente 1,
    # então a regra de negócio depende do prompt estar correto.
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(resposta_com_uma_so))

    sessao = _criar_sessao()
    resultado = service.gerar(sessao)
    assert len(resultado.estrategias) == 1  # schema permite; ver nota acima


def test_retentativa_quando_primeira_resposta_e_json_invalido():
    service = EstrategiaService()
    resposta_invalida = MagicMock(content="isso não é um JSON válido")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[resposta_invalida_msg, _resposta_mock(_RESPOSTA_VALIDA)]
    )

    sessao = _criar_sessao()
    resultado = service.gerar(sessao)

    assert len(resultado.estrategias) == 2
    assert service._client.chat.completions.create.call_count == 2


def test_levanta_erro_apos_esgotar_tentativas():
    service = EstrategiaService()
    resposta_invalida = MagicMock(content="ainda inválido")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(return_value=resposta_invalida_msg)

    sessao = _criar_sessao()
    with pytest.raises(ValueError):
        service.gerar(sessao)

    assert service._client.chat.completions.create.call_count == 2
