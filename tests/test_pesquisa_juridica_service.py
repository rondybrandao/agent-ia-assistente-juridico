import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.schemas import (
    AreaDireito,
    DadosContato,
    ResumoTriagem,
    SessaoConversa,
    Urgencia,
)
from src.services import pesquisa_juridica_service as pesquisa_module
from src.services.pesquisa_juridica_service import PesquisaJuridicaService


def _criar_sessao() -> SessaoConversa:
    return SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217", nome="Cliente Teste"),
        resumo_atual=ResumoTriagem(
            area_direito=AreaDireito.TRABALHISTA,
            resumo_caso="Demissão sem justa causa em março de 2024.",
            urgencia=Urgencia.MEDIA,
        ),
    )


def _resposta_sem_ferramenta(texto: str):
    msg = MagicMock(content=texto, tool_calls=None)
    return MagicMock(choices=[MagicMock(message=msg)])


def _resposta_com_ferramenta(query: str, call_id: str = "call_1"):
    tool_call = MagicMock()
    tool_call.id = call_id
    tool_call.function.arguments = json.dumps({"query": query})
    tool_call.model_dump.return_value = {
        "id": call_id,
        "type": "function",
        "function": {"name": "buscar_na_web", "arguments": tool_call.function.arguments},
    }
    msg = MagicMock(content=None, tool_calls=[tool_call])
    return MagicMock(choices=[MagicMock(message=msg)])


@pytest.mark.asyncio
async def test_pergunta_simples_sem_precisar_de_busca(monkeypatch):
    service = PesquisaJuridicaService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_sem_ferramenta("Recomendo pleitear verbas rescisórias e FGTS.")
    )

    sessao = _criar_sessao()
    resposta = await service.perguntar(sessao, "Quais verbas o cliente pode pleitear?")

    assert resposta == "Recomendo pleitear verbas rescisórias e FGTS."
    # a pergunta e a resposta ficam registradas no histórico de pesquisa
    assert len(sessao.historico_pesquisa) == 2
    assert sessao.historico_pesquisa[0].remetente == "advogado"
    assert sessao.historico_pesquisa[1].remetente == "assistente_pesquisa"


@pytest.mark.asyncio
async def test_pergunta_que_aciona_busca_na_web(monkeypatch):
    service = PesquisaJuridicaService()
    service._client.chat.completions.create = MagicMock(
        side_effect=[
            _resposta_com_ferramenta("prazo prescricional ação trabalhista 2026"),
            _resposta_sem_ferramenta("O prazo prescricional é de 2 anos após o fim do contrato."),
        ]
    )

    mock_buscar = AsyncMock(
        return_value=[
            {
                "titulo": "Prescrição trabalhista - artigo",
                "url": "https://exemplo.com/artigo",
                "conteudo": "O prazo prescricional trabalhista é de dois anos...",
            }
        ]
    )
    monkeypatch.setattr(pesquisa_module.web_search_client, "buscar", mock_buscar)

    sessao = _criar_sessao()
    resposta = await service.perguntar(sessao, "Qual o prazo prescricional desse caso?")

    assert "2 anos" in resposta
    mock_buscar.assert_awaited_once_with("prazo prescricional ação trabalhista 2026")
    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_contexto_do_caso_e_enviado_ao_modelo(monkeypatch):
    service = PesquisaJuridicaService()
    mock_create = MagicMock(return_value=_resposta_sem_ferramenta("ok"))
    service._client.chat.completions.create = mock_create

    sessao = _criar_sessao()
    await service.perguntar(sessao, "Alguma sugestão?")

    mensagens_enviadas = mock_create.call_args.kwargs["messages"]
    contexto = "\n".join(m["content"] for m in mensagens_enviadas if m["role"] == "system")
    assert "Demissão sem justa causa" in contexto
    assert "trabalhista" in contexto


def test_contexto_mostra_qualificacao_incompleta():
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    sessao = _criar_sessao()  # dados_pessoais_autor vazio por padrão
    contexto = _montar_contexto_caso(sessao)

    assert "INCOMPLETA" in contexto
    assert "CPF" in contexto


def test_contexto_mostra_qualificacao_completa():
    from src.domain.schemas import DadosPessoaisAutor
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    sessao = _criar_sessao()
    sessao.resumo_atual.dados_pessoais_autor = DadosPessoaisAutor(
        nome="Cliente Teste",
        nacionalidade="brasileira",
        estado_civil="solteiro",
        profissao="motorista",
        cpf="123.456.789-00",
        rg="1234567",
        endereco_completo="Rua X, 123",
        cep="69000-000",
        cidade="Manaus",
        data_nascimento="1990-01-01",
    )
    contexto = _montar_contexto_caso(sessao)

    assert "Completa" in contexto
    assert "INCOMPLETA" not in contexto


def test_contexto_sem_peticao_gerada_avisa_isso(monkeypatch, tmp_path):
    from src.repositories.peca_repository import PecaRepository
    from src.services import pesquisa_juridica_service as modulo
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    repo_teste = PecaRepository(db_path=str(tmp_path / "test.db"))
    monkeypatch.setattr(modulo, "peca_repository", repo_teste)

    sessao = _criar_sessao()
    contexto = _montar_contexto_caso(sessao)

    assert "Nenhuma petição foi gerada ainda para este caso" in contexto


def test_contexto_mostra_campos_pendentes_da_peticao_mais_recente(monkeypatch, tmp_path):
    """O cenário exato pedido: 'quais informações estão faltando para
    concluir a petição inicial?' precisa encontrar isso no contexto."""
    from src.domain.peticao_schemas import Peca
    from src.repositories.peca_repository import PecaRepository
    from src.services import pesquisa_juridica_service as modulo
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    repo_teste = PecaRepository(db_path=str(tmp_path / "test.db"))
    repo_teste.salvar(
        Peca(
            peca_id="p1",
            telefone="5592984705217",
            template_id="civel_indenizatoria_erro_medico",
            titulo="Ação de Indenização",
            peca_texto="...",
            campos_pendentes=["CPF do autor", "endereço completo do réu"],
        )
    )
    monkeypatch.setattr(modulo, "peca_repository", repo_teste)

    sessao = _criar_sessao()
    contexto = _montar_contexto_caso(sessao)

    assert "Ação de Indenização" in contexto
    assert "CPF do autor" in contexto
    assert "endereço completo do réu" in contexto


def test_contexto_peticao_sem_pendencias_diz_isso_explicitamente(monkeypatch, tmp_path):
    from src.domain.peticao_schemas import Peca
    from src.repositories.peca_repository import PecaRepository
    from src.services import pesquisa_juridica_service as modulo
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    repo_teste = PecaRepository(db_path=str(tmp_path / "test.db"))
    repo_teste.salvar(
        Peca(
            peca_id="p1",
            telefone="5592984705217",
            template_id="x",
            titulo="Peça completa",
            peca_texto="...",
            campos_pendentes=[],
        )
    )
    monkeypatch.setattr(modulo, "peca_repository", repo_teste)

    sessao = _criar_sessao()
    contexto = _montar_contexto_caso(sessao)

    assert "Nenhum campo pendente sinalizado" in contexto


def test_contexto_mostra_estrategia_escolhida_marcada():
    from src.domain.estrategia_schemas import (
        EstimativaCusto,
        EstimativaPrazo,
        Estrategia,
        RespostaEstrategias,
        TutelaUrgencia,
    )
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    estrategia = Estrategia(
        id="A",
        nome="Juizado Especial",
        via="judicial",
        rito="juizado_especial",
        eixos_de_diferenca=["RITO"],
        resumo="...",
        tutela_urgencia=TutelaUrgencia(cabivel=False, justificativa="-"),
        estimativa_custo=EstimativaCusto(custas="-", honorarios_sucumbencia="-", observacao="-"),
        estimativa_prazo=EstimativaPrazo(faixa="-", base="-"),
        probabilidade_qualitativa="media",
        justificativa_probabilidade="-",
        quando_escolher="-",
    )
    sessao = _criar_sessao()
    sessao.ultimas_estrategias = RespostaEstrategias(estrategias=[estrategia], aviso="-")
    sessao.estrategia_escolhida = estrategia

    contexto = _montar_contexto_caso(sessao)

    assert "[ESCOLHIDA]" in contexto
    assert "Juizado Especial" in contexto


def test_contexto_mostra_valor_da_causa_e_alerta_de_correcao_pendente():
    from datetime import date

    from src.domain.valor_causa_schemas import RespostaValorCausa
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    sessao = _criar_sessao()
    sessao.ultimo_calculo_valor_causa = RespostaValorCausa(
        subtotal_componentes=8000.0,
        valor_da_causa=8000.0,
        ha_correcao_monetaria_pendente=True,
        data_calculo=date(2026, 1, 1),
    )

    contexto = _montar_contexto_caso(sessao)

    assert "8000.00" in contexto
    assert "correção monetária pendente" in contexto


def test_contexto_mostra_prazo_calculado():
    from datetime import date

    from src.domain.prazo_schemas import RegimePrazo, RespostaPrazo
    from src.services.pesquisa_juridica_service import _montar_contexto_caso

    sessao = _criar_sessao()
    sessao.ultimo_prazo_calculado = RespostaPrazo(
        data_intimacao=date(2026, 3, 6),
        dias_solicitados=15,
        dias_efetivos=15,
        regime=RegimePrazo.CPC,
        fundamento_regime="CPC art. 219",
        data_inicio_contagem=date(2026, 3, 9),
        data_vencimento=date(2026, 3, 27),
        alerta_recesso_forense=False,
    )

    contexto = _montar_contexto_caso(sessao)

    assert "2026-03-27" in contexto
