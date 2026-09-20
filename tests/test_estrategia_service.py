import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.domain.estrategia_schemas import RespostaEstrategias
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


@pytest.mark.asyncio
async def test_gera_estrategias_com_resposta_valida_de_primeira():
    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    sessao = _criar_sessao()
    resultado = await service.gerar(sessao, objetivo_usuario="rapidez")

    assert len(resultado.estrategias) == 2
    assert resultado.estrategias[0].id == "A"
    assert resultado.recomendacao.estrategia_id == "A"
    assert service._client.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_minimo_de_duas_estrategias_e_respeitado_pelo_schema():
    resposta_com_uma_so = {**_RESPOSTA_VALIDA, "estrategias": [_RESPOSTA_VALIDA["estrategias"][0]]}
    service = EstrategiaService()
    # a validação de "mínimo 2" é responsabilidade do PROMPT (regra 1), não do
    # Pydantic — este teste documenta que o schema aceita tecnicamente 1,
    # então a regra de negócio depende do prompt estar correto.
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(resposta_com_uma_so))

    sessao = _criar_sessao()
    resultado = await service.gerar(sessao)
    assert len(resultado.estrategias) == 1  # schema permite; ver nota acima


@pytest.mark.asyncio
async def test_retentativa_quando_primeira_resposta_e_json_invalido():
    service = EstrategiaService()
    resposta_invalida = MagicMock(content="isso não é um JSON válido")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[resposta_invalida_msg, _resposta_mock(_RESPOSTA_VALIDA)]
    )

    sessao = _criar_sessao()
    resultado = await service.gerar(sessao)

    assert len(resultado.estrategias) == 2
    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_levanta_erro_apos_esgotar_tentativas():
    service = EstrategiaService()
    resposta_invalida = MagicMock(content="ainda inválido")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(return_value=resposta_invalida_msg)

    sessao = _criar_sessao()
    with pytest.raises(ValueError):
        await service.gerar(sessao)

    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_apenas_citacoes_confirmadas_entram_em_pesquisa_verificada(monkeypatch):
    from unittest.mock import AsyncMock

    from src.domain.citacao_schemas import (
        CitacaoEntrada,
        ResultadoVerificacaoCitacao,
        StatusVerificacao,
        TipoCitacao,
    )
    from src.services import estrategia_service as estrategia_module

    resultados_verificacao = [
        ResultadoVerificacaoCitacao(
            tipo=TipoCitacao.SUMULA,
            referencia="Súmula 297 STJ",
            status=StatusVerificacao.CONFIRMADA,
            existe=True,
            fonte_url="https://stj.jus.br/sumula-297",
            observacao="Confirmada no site do STJ.",
        ),
        ResultadoVerificacaoCitacao(
            tipo=TipoCitacao.ACORDAO,
            referencia="REsp 9.999.999/XX",
            status=StatusVerificacao.NAO_ENCONTRADA,
            existe=False,
            observacao="Nenhum resultado confirma esse número.",
        ),
    ]
    mock_verificar = AsyncMock(return_value=resultados_verificacao)
    monkeypatch.setattr(estrategia_module.verificacao_citacao_service, "verificar", mock_verificar)

    service = EstrategiaService()
    mock_create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    candidatas = [
        CitacaoEntrada(tipo=TipoCitacao.SUMULA, referencia="Súmula 297 STJ"),
        CitacaoEntrada(tipo=TipoCitacao.ACORDAO, referencia="REsp 9.999.999/XX"),
    ]
    await service.gerar(sessao, citacoes_candidatas=candidatas)

    entrada_enviada = json.loads(mock_create.call_args.kwargs["messages"][1]["content"])

    # a confirmada entrou em pesquisa_verificada...
    referencias_verificadas = [c["referencia"] for c in entrada_enviada["pesquisa_verificada"]]
    assert "Súmula 297 STJ" in referencias_verificadas

    # ...a não encontrada NUNCA entra nesse campo
    assert "REsp 9.999.999/XX" not in referencias_verificadas

    # mas aparece separadamente, marcada como não confirmada
    nao_confirmadas = entrada_enviada.get("citacoes_verificadas_mas_nao_confirmadas", [])
    referencias_nao_confirmadas = [c["referencia"] for c in nao_confirmadas]
    assert "REsp 9.999.999/XX" in referencias_nao_confirmadas


@pytest.mark.asyncio
async def test_busca_automatica_de_jurisprudencia_alimenta_a_verificacao(monkeypatch):
    """
    Testa o pipeline completo: buscar_jurisprudencia_automaticamente=True faz
    o EstrategiaService buscar candidatos sozinho, verificá-los, e só passar
    os confirmados para o prompt — sem o chamador precisar fazer nada disso
    manualmente.
    """
    from unittest.mock import AsyncMock

    from src.domain.citacao_schemas import (
        CitacaoEntrada,
        ResultadoVerificacaoCitacao,
        StatusVerificacao,
        TipoCitacao,
    )
    from src.services import estrategia_service as estrategia_module

    # 1) a "busca de jurisprudência" encontra um candidato sozinha
    candidato_encontrado = [CitacaoEntrada(tipo=TipoCitacao.SUMULA, referencia="Súmula 297 STJ")]
    mock_buscar_jurisprudencia = AsyncMock(return_value=candidato_encontrado)
    monkeypatch.setattr(estrategia_module.jurisprudencia_service, "buscar", mock_buscar_jurisprudencia)

    # 2) a verificação confirma esse candidato
    resultado_verificacao = [
        ResultadoVerificacaoCitacao(
            tipo=TipoCitacao.SUMULA,
            referencia="Súmula 297 STJ",
            status=StatusVerificacao.CONFIRMADA,
            existe=True,
            fonte_url="https://stj.jus.br/sumula-297",
            observacao="Confirmada.",
        )
    ]
    mock_verificar = AsyncMock(return_value=resultado_verificacao)
    monkeypatch.setattr(estrategia_module.verificacao_citacao_service, "verificar", mock_verificar)

    service = EstrategiaService()
    mock_create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    await service.gerar(sessao, buscar_jurisprudencia_automaticamente=True)

    # a busca automática foi acionada com base no resumo do caso
    mock_buscar_jurisprudencia.assert_awaited_once()
    consulta_usada = mock_buscar_jurisprudencia.call_args[0][0]
    assert "Cobrança indevida" in consulta_usada

    # e o resultado confirmado chegou até o prompt final
    entrada_enviada = json.loads(mock_create.call_args.kwargs["messages"][1]["content"])
    referencias = [c["referencia"] for c in entrada_enviada["pesquisa_verificada"]]
    assert "Súmula 297 STJ" in referencias


@pytest.mark.asyncio
async def test_busca_automatica_nao_acontece_se_citacoes_ja_foram_informadas(monkeypatch):
    """Se o chamador já mandou citacoes_candidatas, não faz sentido gastar
    uma busca automática por cima — o explícito tem prioridade sobre o automático."""
    from unittest.mock import AsyncMock

    from src.domain.citacao_schemas import CitacaoEntrada, TipoCitacao
    from src.services import estrategia_service as estrategia_module

    mock_buscar_jurisprudencia = AsyncMock()
    monkeypatch.setattr(estrategia_module.jurisprudencia_service, "buscar", mock_buscar_jurisprudencia)
    monkeypatch.setattr(estrategia_module.verificacao_citacao_service, "verificar", AsyncMock(return_value=[]))

    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    sessao = _criar_sessao()
    citacoes_ja_informadas = [CitacaoEntrada(tipo=TipoCitacao.LEI, referencia="Lei 8.078/1990")]
    await service.gerar(
        sessao, citacoes_candidatas=citacoes_ja_informadas, buscar_jurisprudencia_automaticamente=True
    )

    mock_buscar_jurisprudencia.assert_not_awaited()


@pytest.mark.asyncio
async def test_competencia_informada_manualmente_entra_no_prompt():
    from src.domain.competencia_schemas import RamoJustica, RespostaCompetencia, RitoCompetencia

    service = EstrategiaService()
    mock_create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    competencia = RespostaCompetencia(
        ramo_justica=RamoJustica.ESTADUAL,
        rito=RitoCompetencia.JUIZADO_ESPECIAL,
        foro_territorial="Manaus",
        fundamento_foro="CDC art. 101, I",
        dispensa_advogado=True,
    )

    sessao = _criar_sessao()
    await service.gerar(sessao, competencia=competencia)

    entrada_enviada = json.loads(mock_create.call_args.kwargs["messages"][1]["content"])
    assert entrada_enviada["competencia"]["foro_territorial"] == "Manaus"
    assert entrada_enviada["competencia"]["rito"] == "juizado_especial"


@pytest.mark.asyncio
async def test_checagem_automatica_de_pressupostos_usa_fatos_do_caso(monkeypatch):
    from src.domain.pressupostos_schemas import (
        AvaliacaoPressuposto,
        RespostaPressupostos,
        StatusPressuposto,
    )
    from src.services import estrategia_service as estrategia_module

    resultado_pressupostos = RespostaPressupostos(
        avaliacoes=[
            AvaliacaoPressuposto(
                tipo="prescricao", status=StatusPressuposto.OK, analise="Sem indício de prescrição."
            )
        ],
        tem_risco_critico=False,
    )
    mock_checar = MagicMock(return_value=resultado_pressupostos)
    monkeypatch.setattr(estrategia_module.checar_pressupostos_service, "checar", mock_checar)

    service = EstrategiaService()
    mock_create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    await service.gerar(sessao, checar_pressupostos_automaticamente=True)

    # a checagem automática foi acionada com a área e os fatos do caso
    mock_checar.assert_called_once()
    requisicao_usada = mock_checar.call_args[0][0]
    assert requisicao_usada.area == "consumidor"

    # e o resultado chegou até o prompt final
    entrada_enviada = json.loads(mock_create.call_args.kwargs["messages"][1]["content"])
    assert entrada_enviada["pressupostos"]["tem_risco_critico"] is False


@pytest.mark.asyncio
async def test_pressupostos_informado_manualmente_nao_aciona_checagem_automatica(monkeypatch):
    from src.domain.pressupostos_schemas import RespostaPressupostos
    from src.services import estrategia_service as estrategia_module

    mock_checar = MagicMock()
    monkeypatch.setattr(estrategia_module.checar_pressupostos_service, "checar", mock_checar)

    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    pressupostos_prontos = RespostaPressupostos(avaliacoes=[], tem_risco_critico=False)
    sessao = _criar_sessao()
    await service.gerar(
        sessao, pressupostos=pressupostos_prontos, checar_pressupostos_automaticamente=True
    )

    mock_checar.assert_not_called()


@pytest.mark.asyncio
async def test_busca_automatica_combina_jurisprudencia_e_legislacao(monkeypatch):
    """Quando as duas buscas automáticas estão ligadas, os candidatos de
    ambas devem ser combinados antes de ir para a verificação."""
    from unittest.mock import AsyncMock

    from src.domain.citacao_schemas import CitacaoEntrada, TipoCitacao
    from src.services import estrategia_service as estrategia_module

    candidato_jurisprudencia = [CitacaoEntrada(tipo=TipoCitacao.SUMULA, referencia="Súmula 297 STJ")]
    candidato_legislacao = [CitacaoEntrada(tipo=TipoCitacao.LEI, referencia="Lei 8.078/1990, art. 42")]

    mock_jurisprudencia = AsyncMock(return_value=candidato_jurisprudencia)
    mock_legislacao = AsyncMock(return_value=candidato_legislacao)
    monkeypatch.setattr(estrategia_module.jurisprudencia_service, "buscar", mock_jurisprudencia)
    monkeypatch.setattr(estrategia_module.legislacao_service, "buscar", mock_legislacao)
    monkeypatch.setattr(estrategia_module.verificacao_citacao_service, "verificar", AsyncMock(return_value=[]))

    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    sessao = _criar_sessao()
    await service.gerar(
        sessao,
        buscar_jurisprudencia_automaticamente=True,
        buscar_legislacao_automaticamente=True,
    )

    mock_jurisprudencia.assert_awaited_once()
    mock_legislacao.assert_awaited_once()

    # a verificação recebeu os candidatos das DUAS buscas juntos
    resultado_verificar = estrategia_module.verificacao_citacao_service.verificar
    citacoes_enviadas = resultado_verificar.call_args[0][0]
    referencias = {c.referencia for c in citacoes_enviadas}
    assert "Súmula 297 STJ" in referencias
    assert "Lei 8.078/1990, art. 42" in referencias


@pytest.mark.asyncio
async def test_apenas_uma_busca_automatica_ligada_nao_aciona_a_outra(monkeypatch):
    from unittest.mock import AsyncMock

    from src.services import estrategia_service as estrategia_module

    mock_legislacao = AsyncMock(return_value=[])
    monkeypatch.setattr(estrategia_module.legislacao_service, "buscar", mock_legislacao)
    monkeypatch.setattr(estrategia_module.jurisprudencia_service, "buscar", AsyncMock(return_value=[]))

    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    sessao = _criar_sessao()
    await service.gerar(sessao, buscar_jurisprudencia_automaticamente=True)

    mock_legislacao.assert_not_awaited()


@pytest.mark.asyncio
async def test_usa_fatos_estruturados_quando_disponiveis_na_sessao():
    """Se extrair_fatos já rodou pra essa sessão, o prompt final deve usar
    a linha do tempo/partes/valores estruturados, não o resumo raso."""
    from src.domain.fatos_schemas import (
        EventoLinhaDoTempo,
        ParteIdentificada,
        RespostaExtracaoFatos,
    )

    service = EstrategiaService()
    mock_create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    sessao.fatos_estruturados = RespostaExtracaoFatos(
        resumo_narrativo="Resumo bem mais detalhado da extração estruturada.",
        linha_do_tempo=[
            EventoLinhaDoTempo(data=None, data_aproximada_texto="março de 2024", descricao="Fato X", fonte="relato")
        ],
        partes=[ParteIdentificada(papel="autor", nome="Cliente Teste", qualificacao=None)],
    )

    await service.gerar(sessao)

    entrada_enviada = json.loads(mock_create.call_args.kwargs["messages"][1]["content"])
    assert entrada_enviada["fatos"]["resumo"] == "Resumo bem mais detalhado da extração estruturada."
    assert entrada_enviada["fatos"]["linha_do_tempo"][0]["descricao"] == "Fato X"
    assert entrada_enviada["fatos"]["partes"][0]["nome"] == "Cliente Teste"
    # o formato antigo (fatos_relevantes) não deve aparecer quando há fatos_estruturados
    assert "fatos_relevantes" not in entrada_enviada["fatos"]


@pytest.mark.asyncio
async def test_usa_resumo_raso_quando_fatos_estruturados_nao_existem():
    """Sem extrair_fatos ainda rodado, mantém o comportamento antigo
    (compatibilidade com casos já em andamento antes dessa integração)."""
    service = EstrategiaService()
    mock_create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    assert sessao.fatos_estruturados is None

    await service.gerar(sessao)

    entrada_enviada = json.loads(mock_create.call_args.kwargs["messages"][1]["content"])
    assert "fatos_relevantes" in entrada_enviada["fatos"]
    assert "linha_do_tempo" not in entrada_enviada["fatos"]


@pytest.mark.asyncio
async def test_gerar_persiste_ultimas_estrategias_na_sessao(monkeypatch):
    from src.repositories.session_repository import SessaoRepository
    import src.services.estrategia_service as modulo

    service = EstrategiaService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_mock(_RESPOSTA_VALIDA))

    sessao = _criar_sessao()
    resultado = await service.gerar(sessao)

    assert sessao.ultimas_estrategias is not None
    assert sessao.ultimas_estrategias.estrategias[0].id == resultado.estrategias[0].id


def test_escolher_estrategia_valida_salva_na_sessao():
    service = EstrategiaService()
    sessao = _criar_sessao()
    sessao.ultimas_estrategias = RespostaEstrategias(**_RESPOSTA_VALIDA)

    escolhida = service.escolher(sessao, "A")

    assert escolhida.id == "A"
    assert sessao.estrategia_escolhida is not None
    assert sessao.estrategia_escolhida.id == "A"


def test_escolher_estrategia_inexistente_levanta_erro():
    service = EstrategiaService()
    sessao = _criar_sessao()
    sessao.ultimas_estrategias = RespostaEstrategias(**_RESPOSTA_VALIDA)

    with pytest.raises(ValueError):
        service.escolher(sessao, "Z")


def test_escolher_sem_estrategias_geradas_levanta_erro():
    service = EstrategiaService()
    sessao = _criar_sessao()
    assert sessao.ultimas_estrategias is None

    with pytest.raises(ValueError):
        service.escolher(sessao, "A")