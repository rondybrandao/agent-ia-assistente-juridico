import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.domain.peticao_schemas import CitacaoParaPeca, PeticaoRequest
from src.services.peticao_service import (
    PeticaoService,
    _montar_esqueleto,
    _resolver_blocos_condicionais,
    _SYSTEM_PROMPT,
    _TEMPLATES_DATA,
)


def _resposta_llm(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def test_todos_os_templates_expandem_sem_sobrar_bloco_nao_resolvido():
    entrada_generica = PeticaoRequest(
        template_id="x",
        valor_causa=1000,
        partes={"possui_advogado": True, "pede_gratuidade": True, "autor_tipo": "pessoa_fisica"},
    )
    blocos = _resolver_blocos_condicionais(_TEMPLATES_DATA["blocos_reutilizaveis"], entrada_generica)

    for template in _TEMPLATES_DATA["templates"]:
        esqueleto = _montar_esqueleto(template, blocos)
        assert "{{bloco:" not in esqueleto, f"Sobrou bloco não resolvido em {template['template_id']}"


def test_sem_gratuidade_o_bloco_correspondente_fica_vazio():
    entrada = PeticaoRequest(template_id="x", valor_causa=1000, partes={"pede_gratuidade": False})
    blocos = _resolver_blocos_condicionais(_TEMPLATES_DATA["blocos_reutilizaveis"], entrada)
    assert blocos["gratuidade_se_aplicavel"] == ""


def test_com_gratuidade_o_bloco_e_preenchido():
    entrada = PeticaoRequest(template_id="x", valor_causa=1000, partes={"pede_gratuidade": True})
    blocos = _resolver_blocos_condicionais(_TEMPLATES_DATA["blocos_reutilizaveis"], entrada)
    assert "hipossuficiência" in blocos["gratuidade_se_aplicavel"]


def test_sem_advogado_usa_fecho_sem_advogado():
    entrada = PeticaoRequest(template_id="x", valor_causa=1000, partes={"possui_advogado": False})
    blocos = _resolver_blocos_condicionais(_TEMPLATES_DATA["blocos_reutilizaveis"], entrada)
    assert "CPF {{cpf}}" in blocos["fecho_ou_fecho_sem_advogado"]  # fecho_sem_advogado tem esse trecho


def test_buscar_template_inexistente_levanta_erro():
    service = PeticaoService()
    with pytest.raises(ValueError):
        service.buscar_template("nao_existe")


def test_listar_templates_retorna_os_6_templates_com_campos_basicos():
    service = PeticaoService()
    templates = service.listar_templates()
    assert len(templates) == 6
    ids = {t["template_id"] for t in templates}
    assert "consumo_indenizatoria_jec" in ids
    assert "trabalhista_reclamacao" in ids
    assert "civel_indenizatoria_erro_medico" in ids


@pytest.mark.asyncio
async def test_gerar_peticao_com_resposta_valida():
    service = PeticaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "peca_texto": "EXCELENTÍSSIMO... (peça completa preenchida)",
                "campos_pendentes": ["endereco_reu"],
            }
        )
    )

    entrada = PeticaoRequest(
        template_id="consumo_indenizatoria_jec",
        valor_causa=8000,
        fatos={"resumo": "Cobrança indevida de R$ 8.000 no cartão."},
        partes={"nome_autor": "Cliente Teste", "possui_advogado": True},
        competencia={"comarca": "Manaus"},
        citacoes_verificadas=[
            CitacaoParaPeca(tipo="sumula", referencia="Súmula 297 STJ", fonte_url="https://stj.jus.br")
        ],
    )

    resultado = await service.gerar(entrada)

    assert resultado.template_id == "consumo_indenizatoria_jec"
    assert "EXCELENTÍSSIMO" in resultado.peca_texto
    assert resultado.campos_pendentes == ["endereco_reu"]
    assert "revisão" in resultado.aviso.lower()


@pytest.mark.asyncio
async def test_apenas_citacoes_verificadas_sao_enviadas_ao_modelo():
    service = PeticaoService()
    mock_create = MagicMock(
        return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []})
    )
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="consumo_indenizatoria_jec",
        valor_causa=8000,
        fatos={},
        partes={},
        competencia={},
        citacoes_verificadas=[
            CitacaoParaPeca(tipo="sumula", referencia="Súmula 297 STJ"),
        ],
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Súmula 297 STJ" in conteudo_enviado
    # nenhuma outra citação foi inventada/adicionada por engano
    assert conteudo_enviado.count('"referencia"') == 1


@pytest.mark.asyncio
async def test_retentativa_quando_json_invalido():
    service = PeticaoService()
    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[
            resposta_invalida_msg,
            _resposta_llm({"peca_texto": "peça corrigida", "campos_pendentes": []}),
        ]
    )

    entrada = PeticaoRequest(template_id="consumo_indenizatoria_jec", valor_causa=1000)
    resultado = await service.gerar(entrada)

    assert resultado.peca_texto == "peça corrigida"
    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_levanta_erro_apos_esgotar_tentativas():
    service = PeticaoService()
    resposta_invalida = MagicMock(content="ainda inválido")
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=resposta_invalida)])
    )

    entrada = PeticaoRequest(template_id="consumo_indenizatoria_jec", valor_causa=1000)
    with pytest.raises(ValueError):
        await service.gerar(entrada)


@pytest.mark.asyncio
async def test_peca_gerada_fica_persistida_e_recuperavel_pelo_id(tmp_path):
    from src.repositories.peca_repository import PecaRepository

    db_path = str(tmp_path / "test.db")
    repo_teste = PecaRepository(db_path=db_path)

    service = PeticaoService()
    import src.services.peticao_service as peticao_module

    original_repo = peticao_module.peca_repository
    peticao_module.peca_repository = repo_teste
    try:
        service._client.chat.completions.create = MagicMock(
            return_value=_resposta_llm({"peca_texto": "texto da peça", "campos_pendentes": []})
        )
        entrada = PeticaoRequest(template_id="consumo_indenizatoria_jec", valor_causa=1000)
        resultado = await service.gerar(entrada)

        assert resultado.peca_id  # não vazio
        peca_salva = repo_teste.buscar(resultado.peca_id)
        assert peca_salva is not None
        assert peca_salva.peca_texto == "texto da peça"
    finally:
        peticao_module.peca_repository = original_repo


@pytest.mark.asyncio
async def test_estrategia_escolhida_e_enviada_ao_modelo():
    """Quando o advogado já escolheu uma estratégia, ela precisa chegar
    até o prompt de preenchimento — é isso que alinha os pedidos da peça
    com o caminho jurídico escolhido."""
    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    estrategia = {
        "id": "A",
        "nome": "Juizado Especial com pedido enxuto",
        "via": "judicial",
        "rito": "juizado_especial",
        "pedidos_principais": ["Restituição em dobro"],
        "quando_escolher": "Quando o objetivo é rapidez.",
    }
    entrada = PeticaoRequest(
        template_id="consumo_indenizatoria_jec",
        valor_causa=8000,
        estrategia_escolhida=estrategia,
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Juizado Especial com pedido enxuto" in conteudo_enviado


@pytest.mark.asyncio
async def test_telefone_auto_preenche_estrategia_escolhida_do_caso(monkeypatch, tmp_path):
    """Se o chamador não mandou estrategia_escolhida manualmente, mas
    informou o telefone de um caso que já tem uma estratégia escolhida,
    o peticao_service deve puxar ela sozinho."""
    from src.domain.estrategia_schemas import (
        EstimativaCusto,
        EstimativaPrazo,
        Estrategia,
        TutelaUrgencia,
    )
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    estrategia = Estrategia(
        id="A",
        nome="Juizado Especial com pedido enxuto",
        via="judicial",
        rito="juizado_especial",
        eixos_de_diferenca=["RITO"],
        resumo="...",
        tutela_urgencia=TutelaUrgencia(cabivel=False, justificativa="-"),
        estimativa_custo=EstimativaCusto(custas="-", honorarios_sucumbencia="-", observacao="-"),
        estimativa_prazo=EstimativaPrazo(faixa="-", base="-"),
        probabilidade_qualitativa="media",
        justificativa_probabilidade="-",
        quando_escolher="Quando o objetivo é rapidez.",
    )
    sessao = SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217"),
        estrategia_escolhida=estrategia,
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="consumo_indenizatoria_jec", valor_causa=8000, telefone="5592984705217"
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Juizado Especial com pedido enxuto" in conteudo_enviado


@pytest.mark.asyncio
async def test_estrategia_manual_tem_prioridade_sobre_a_do_caso(monkeypatch, tmp_path):
    """Se o chamador JÁ mandou estrategia_escolhida manualmente, o telefone
    não deve sobrescrever com a estratégia salva no caso."""
    from src.domain.estrategia_schemas import (
        EstimativaCusto,
        EstimativaPrazo,
        Estrategia,
        TutelaUrgencia,
    )
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    estrategia_do_caso = Estrategia(
        id="B",
        nome="Estratégia salva no caso (não deveria aparecer)",
        via="judicial",
        rito="comum",
        eixos_de_diferenca=["RITO"],
        resumo="...",
        tutela_urgencia=TutelaUrgencia(cabivel=False, justificativa="-"),
        estimativa_custo=EstimativaCusto(custas="-", honorarios_sucumbencia="-", observacao="-"),
        estimativa_prazo=EstimativaPrazo(faixa="-", base="-"),
        probabilidade_qualitativa="media",
        justificativa_probabilidade="-",
        quando_escolher="-",
    )
    sessao = SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217"),
        estrategia_escolhida=estrategia_do_caso,
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="consumo_indenizatoria_jec",
        valor_causa=8000,
        telefone="5592984705217",
        estrategia_escolhida={"nome": "Estratégia manual do chamador"},
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Estratégia manual do chamador" in conteudo_enviado
    assert "não deveria aparecer" not in conteudo_enviado


def test_prompt_distingue_dados_factuais_de_fundamentacao_juridica():
    """Guarda de regressão: fundamentação jurídica e pedidos NÃO podem ser
    tratados como 'dado ausente' — são texto que a IA redige. Sem essa
    distinção no prompt, o campo 'DO DIREITO' inteiro vira [PENDENTE] à
    toa, que foi exatamente o bug relatado."""
    assert "FUNDAMENTAÇÃO JURÍDICA E PEDIDOS" in _SYSTEM_PROMPT
    assert "NÃO é um dado que falta" in _SYSTEM_PROMPT
    assert "fundamentacao_" in _SYSTEM_PROMPT