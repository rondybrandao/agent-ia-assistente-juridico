import json
from unittest.mock import MagicMock

import pytest

from src.domain.pressupostos_schemas import CheckPressupostosRequest, StatusPressuposto
from src.services.pressupostos_service import ChecarPressupostosService

_TIPOS = [
    "prescricao",
    "decadencia",
    "legitimidade",
    "interesse_de_agir",
    "requerimento_administrativo_previo",
    "litispendencia_ou_coisa_julgada",
]


def _resposta_llm(avaliacoes: list):
    msg = MagicMock(content=json.dumps({"avaliacoes": avaliacoes}, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def _avaliacoes_todas_ok():
    return [{"tipo": t, "status": "ok", "analise": "Sem indício de problema.", "dado_faltante": None} for t in _TIPOS]


def test_todos_pressupostos_ok_nao_tem_risco_critico():
    service = ChecarPressupostosService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(_avaliacoes_todas_ok()))

    entrada = CheckPressupostosRequest(area="civel", fatos={"resumo": "Caso qualquer"})
    resultado = service.checar(entrada)

    assert resultado.tem_risco_critico is False
    assert len(resultado.avaliacoes) == 6


def test_prescricao_com_risco_marca_tem_risco_critico():
    service = ChecarPressupostosService()
    avaliacoes = _avaliacoes_todas_ok()
    avaliacoes[0] = {
        "tipo": "prescricao",
        "status": "risco",
        "analise": "O último fato ocorreu há mais de 5 anos, prazo comum de prescrição cível.",
        "dado_faltante": None,
    }
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(avaliacoes))

    entrada = CheckPressupostosRequest(
        area="civel", fatos={"resumo": "Dívida antiga"}, data_ultimo_fato="2018-01-01"
    )
    resultado = service.checar(entrada)

    assert resultado.tem_risco_critico is True
    item_prescricao = next(a for a in resultado.avaliacoes if a.tipo == "prescricao")
    assert item_prescricao.status == StatusPressuposto.RISCO


def test_lacuna_nao_conta_como_risco_critico():
    """Falta de dado é diferente de risco real — não deve disparar o alerta."""
    service = ChecarPressupostosService()
    avaliacoes = _avaliacoes_todas_ok()
    avaliacoes[0] = {
        "tipo": "prescricao",
        "status": "lacuna",
        "analise": "Não é possível avaliar sem a data do fato.",
        "dado_faltante": "data do fato gerador",
    }
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(avaliacoes))

    entrada = CheckPressupostosRequest(area="civel", fatos={})
    resultado = service.checar(entrada)

    assert resultado.tem_risco_critico is False


def test_retentativa_quando_json_invalido():
    service = ChecarPressupostosService()
    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[resposta_invalida_msg, _resposta_llm(_avaliacoes_todas_ok())]
    )

    entrada = CheckPressupostosRequest(area="civel", fatos={})
    resultado = service.checar(entrada)

    assert len(resultado.avaliacoes) == 6
    assert service._client.chat.completions.create.call_count == 2


def test_levanta_erro_apos_esgotar_tentativas():
    service = ChecarPressupostosService()
    resposta_invalida = MagicMock(content="ainda inválido")
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=resposta_invalida)])
    )

    entrada = CheckPressupostosRequest(area="civel", fatos={})
    with pytest.raises(ValueError):
        service.checar(entrada)
