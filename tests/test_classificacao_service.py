import json
from unittest.mock import MagicMock

import pytest

from src.domain.classificacao_schemas import ClassificarCasoRequest
from src.services.classificacao_service import ClassificacaoService


def _resposta_llm(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def test_classifica_com_template_valido():
    service = ClassificacaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "area_direito": "consumidor",
                "classe_processual_sugerida": "Procedimento do Juizado Especial Cível",
                "assunto_sugerido": "Indenização por Dano Moral",
                "template_id_sugerido": "consumo_indenizatoria_jec",
                "justificativa": "Cobrança indevida em cartão de crédito, típico caso de consumo.",
                "alternativas_consideradas": [],
            }
        )
    )

    entrada = ClassificarCasoRequest(fatos={"resumo": "Cobrança indevida de R$ 8.000 no cartão."})
    resultado = service.classificar(entrada)

    assert resultado.area_direito == "consumidor"
    assert resultado.template_id_sugerido == "consumo_indenizatoria_jec"


def test_template_id_inventado_e_descartado_para_null():
    """Mesmo que o prompt proíba, testamos a salvaguarda de código: um
    template_id que não existe na lista real nunca deve passar disfarçado
    de sugestão válida."""
    service = ClassificacaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "area_direito": "penal",
                "classe_processual_sugerida": "Queixa-crime",
                "assunto_sugerido": "Calúnia",
                "template_id_sugerido": "template_que_nao_existe_123",
                "justificativa": "Caso penal, sem template correspondente cadastrado.",
                "alternativas_consideradas": [],
            }
        )
    )

    entrada = ClassificarCasoRequest(fatos={"resumo": "Caso de calúnia."})
    resultado = service.classificar(entrada)

    assert resultado.template_id_sugerido is None


def test_sem_template_adequado_retorna_null():
    service = ClassificacaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "area_direito": "empresarial",
                "classe_processual_sugerida": "Recuperação Judicial",
                "assunto_sugerido": "Soerguimento de empresa",
                "template_id_sugerido": None,
                "justificativa": "Não há template cadastrado para recuperação judicial.",
                "alternativas_consideradas": [],
            }
        )
    )

    entrada = ClassificarCasoRequest(fatos={"resumo": "Empresa em dificuldade financeira."})
    resultado = service.classificar(entrada)

    assert resultado.template_id_sugerido is None


def test_retentativa_quando_json_invalido():
    service = ClassificacaoService()
    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[
            resposta_invalida_msg,
            _resposta_llm(
                {
                    "area_direito": "trabalhista",
                    "classe_processual_sugerida": "Reclamação Trabalhista",
                    "assunto_sugerido": "Rescisão Indireta",
                    "template_id_sugerido": "trabalhista_reclamacao",
                    "justificativa": "-",
                    "alternativas_consideradas": [],
                }
            ),
        ]
    )

    entrada = ClassificarCasoRequest(fatos={"resumo": "Demissão indireta."})
    resultado = service.classificar(entrada)

    assert resultado.template_id_sugerido == "trabalhista_reclamacao"
    assert service._client.chat.completions.create.call_count == 2


def test_levanta_erro_apos_esgotar_tentativas():
    service = ClassificacaoService()
    resposta_invalida = MagicMock(content="ainda inválido")
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=resposta_invalida)])
    )

    entrada = ClassificarCasoRequest(fatos={"resumo": "Qualquer coisa."})
    with pytest.raises(ValueError):
        service.classificar(entrada)


def test_prompt_lista_apenas_os_5_templates_reais():
    """Confirma que a lista de templates passada ao modelo bate com os
    templates de verdade cadastrados (nada inventado, nada faltando)."""
    service = ClassificacaoService()
    mock_create = MagicMock(
        return_value=_resposta_llm(
            {
                "area_direito": "civel",
                "classe_processual_sugerida": "-",
                "assunto_sugerido": "-",
                "template_id_sugerido": None,
                "justificativa": "-",
                "alternativas_consideradas": [],
            }
        )
    )
    service._client.chat.completions.create = mock_create

    entrada = ClassificarCasoRequest(fatos={"resumo": "Caso genérico."})
    service.classificar(entrada)

    system_prompt_enviado = mock_create.call_args.kwargs["messages"][0]["content"]
    assert "consumo_indenizatoria_jec" in system_prompt_enviado
    assert "trabalhista_reclamacao" in system_prompt_enviado
    assert "previdenciario_beneficio_jef" in system_prompt_enviado
    assert "familia_alimentos" in system_prompt_enviado
    assert "civel_cobranca_comum" in system_prompt_enviado
