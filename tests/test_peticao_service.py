import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.domain.peticao_schemas import CitacaoParaPeca, PeticaoRequest
from src.domain.schemas import AreaDireito, ResumoTriagem
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


@pytest.mark.asyncio
async def test_telefone_auto_preenche_qualificacao_do_autor_ja_coletada(monkeypatch, tmp_path):
    """O bug relatado: nome/CPF/RG/endereço já coletados na conversa
    (chat de novo caso ou triagem WhatsApp) ficavam presos no
    resumo_atual e nunca chegavam na petição. Agora devem ser
    auto-preenchidos em 'partes' quando o telefone do caso é informado."""
    from src.domain.schemas import DadosContato, DadosPessoaisAutor, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.CIVEL,
            dados_pessoais_autor=DadosPessoaisAutor(
                nome="Maria Aparecida Souza",
                nacionalidade="brasileira",
                estado_civil="casada",
                profissao="professora",
                cpf="123.456.789-00",
                rg="1122334-4",
                endereco_completo="Rua das Palmeiras, 245, Educandos",
                cep="69080-000",
                cidade="Manaus",
                data_nascimento="1985-05-10",
            ),
        ),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="civel_indenizatoria_erro_medico",
        valor_causa=50000,
        telefone="manual-abc123",
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Maria Aparecida Souza" in conteudo_enviado
    assert "123.456.789-00" in conteudo_enviado
    assert "Rua das Palmeiras" in conteudo_enviado
    assert "1122334-4" in conteudo_enviado


@pytest.mark.asyncio
async def test_partes_informado_manualmente_tem_prioridade_sobre_o_do_caso(monkeypatch, tmp_path):
    """Se o chamador já mandou 'partes' com um nome diferente, isso não
    deve ser sobrescrito pelo nome salvo na sessão."""
    from src.domain.schemas import DadosContato, DadosPessoaisAutor, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.CIVEL,
            dados_pessoais_autor=DadosPessoaisAutor(nome="Nome da sessão (não deveria aparecer)"),
        ),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="civel_indenizatoria_erro_medico",
        valor_causa=50000,
        telefone="manual-abc123",
        partes={"nome": "Nome manual do chamador"},
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Nome manual do chamador" in conteudo_enviado
    assert "não deveria aparecer" not in conteudo_enviado


@pytest.mark.asyncio
async def test_telefone_auto_preenche_competencia_ja_definida(monkeypatch, tmp_path):
    from src.domain.competencia_schemas import RamoJustica, RespostaCompetencia, RitoCompetencia
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        competencia_definida=RespostaCompetencia(
            ramo_justica=RamoJustica.ESTADUAL,
            rito=RitoCompetencia.COMUM,
            foro_territorial="Manaus",
            fundamento_foro="CPC art. 46",
            dispensa_advogado=False,
        ),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="civel_indenizatoria_erro_medico", valor_causa=50000, telefone="manual-abc123"
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Manaus" in conteudo_enviado
    assert "CPC art. 46" in conteudo_enviado


@pytest.mark.asyncio
async def test_telefone_auto_preenche_valor_causa_ja_calculado(monkeypatch, tmp_path):
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.domain.valor_causa_schemas import RespostaValorCausa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        ultimo_calculo_valor_causa=RespostaValorCausa(
            itens=[], subtotal_componentes=12345.67, valor_da_causa=12345.67,
            ha_correcao_monetaria_pendente=False, data_calculo="2026-01-01",
        ),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(template_id="civel_indenizatoria_erro_medico", telefone="manual-abc123")
    await service.gerar(entrada)

    assert entrada.valor_causa == 12345.67
    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "12345.67" in conteudo_enviado


@pytest.mark.asyncio
async def test_valor_causa_informado_manualmente_tem_prioridade(monkeypatch, tmp_path):
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.domain.valor_causa_schemas import RespostaValorCausa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        ultimo_calculo_valor_causa=RespostaValorCausa(
            itens=[], subtotal_componentes=99999.99, valor_da_causa=99999.99,
            ha_correcao_monetaria_pendente=False, data_calculo="2026-01-01",
        ),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []})
    )

    entrada = PeticaoRequest(
        template_id="civel_indenizatoria_erro_medico", valor_causa=1000.0, telefone="manual-abc123"
    )
    await service.gerar(entrada)

    assert entrada.valor_causa == 1000.0  # não foi sobrescrito pelo valor do caso


@pytest.mark.asyncio
async def test_telefone_auto_preenche_fatos_estruturados_via_construir_fatos_dict(monkeypatch, tmp_path):
    """Confirma que gerar_peticao usa o mesmo método unificado
    construir_fatos_dict() que gerar_estrategias já usava — sem
    duplicação de lógica entre os dois serviços."""
    from src.domain.fatos_schemas import RespostaExtracaoFatos
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        fatos_estruturados=RespostaExtracaoFatos(resumo_narrativo="Resumo bem detalhado do erro médico."),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="civel_indenizatoria_erro_medico", valor_causa=50000, telefone="manual-abc123"
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "Resumo bem detalhado do erro médico" in conteudo_enviado


@pytest.mark.asyncio
async def test_telefone_inclui_prazo_calculado_como_contexto(monkeypatch, tmp_path):
    """calcular_prazos, quando já rodado para o caso, entra como contexto
    de urgência — mas nunca como um dado obrigatório a preencher."""
    from datetime import date

    from src.domain.prazo_schemas import RegimePrazo, RespostaPrazo
    from src.domain.schemas import DadosContato, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.peticao_service as peticao_module

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(peticao_module, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="manual-abc123",
        contato=DadosContato(telefone="manual-abc123"),
        ultimo_prazo_calculado=RespostaPrazo(
            data_intimacao=date(2026, 3, 6),
            dias_solicitados=15,
            dias_efetivos=15,
            regime=RegimePrazo.CPC,
            fundamento_regime="CPC art. 219",
            data_inicio_contagem=date(2026, 3, 9),
            data_vencimento=date(2026, 3, 27),
            alerta_recesso_forense=False,
        ),
    )
    repo_teste.salvar(sessao)

    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(
        template_id="civel_indenizatoria_erro_medico", valor_causa=50000, telefone="manual-abc123"
    )
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "2026-03-27" in conteudo_enviado


@pytest.mark.asyncio
async def test_sem_prazo_calculado_o_campo_fica_nulo():
    """Sem telefone/sem cálculo prévio, 'prazo_calculado' deve ser null —
    nunca um valor inventado."""
    service = PeticaoService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PeticaoRequest(template_id="civel_indenizatoria_erro_medico", valor_causa=50000)
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    dados_enviados = json.loads(conteudo_enviado.split("DADOS DISPONÍVEIS PARA PREENCHIMENTO:\n")[1])
    assert dados_enviados["prazo_calculado"] is None


def test_valor_causa_string_vazia_vira_none_em_vez_de_erro_422():
    """Bug real relatado: o <input type="number"> do Angular manda "" em
    vez de null quando o campo fica vazio — sem essa normalização, o
    Pydantic rejeita com 422 mesmo o campo sendo opcional."""
    entrada = PeticaoRequest(template_id="civel_indenizatoria_erro_medico", valor_causa="")
    assert entrada.valor_causa is None


def test_valor_causa_none_continua_none():
    entrada = PeticaoRequest(template_id="civel_indenizatoria_erro_medico", valor_causa=None)
    assert entrada.valor_causa is None


def test_valor_causa_numerico_nao_e_afetado():
    entrada = PeticaoRequest(template_id="civel_indenizatoria_erro_medico", valor_causa=8000)
    assert entrada.valor_causa == 8000.0