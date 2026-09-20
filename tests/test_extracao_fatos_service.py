import json
from unittest.mock import MagicMock

import pytest

from src.domain.fatos_schemas import ExtrairFatosRequest
from src.services.extracao_fatos_service import ExtracaoFatosService

_RESPOSTA_VALIDA = {
    "resumo_narrativo": "Cliente relata cobrança indevida de R$ 8.000 no cartão de crédito, iniciada em março de 2024.",
    "linha_do_tempo": [
        {
            "data": None,
            "data_aproximada_texto": "início de março de 2024",
            "descricao": "Cliente percebeu cobrança não reconhecida na fatura do cartão.",
            "fonte": "relato",
        },
        {
            "data": None,
            "data_aproximada_texto": "dias depois",
            "descricao": "Cliente contatou o banco, que não resolveu o problema.",
            "fonte": "relato",
        },
    ],
    "partes": [
        {"papel": "autor", "nome": None, "qualificacao": None},
        {"papel": "réu", "nome": "Banco XYZ", "qualificacao": None},
    ],
    "valores_mencionados": [
        {"descricao": "Cobrança indevida no cartão", "valor": 8000.0, "moeda": "BRL", "data_referencia": None}
    ],
    "pontos_controvertidos": [
        {"descricao": "Origem exata da cobrança não identificada", "motivo": "Cliente não sabe explicar de onde veio o valor."}
    ],
    "lacunas": [{"dado_faltante": "Nome completo do cliente", "impacto": "Necessário para qualificação nas peças."}],
}


def _resposta_llm(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def test_extrai_fatos_com_resposta_valida():
    service = ExtracaoFatosService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(_RESPOSTA_VALIDA))

    entrada = ExtrairFatosRequest(relato="Fui cobrado indevidamente em R$ 8.000 no meu cartão pelo Banco XYZ.")
    resultado = service.extrair(entrada)

    assert len(resultado.linha_do_tempo) == 2
    assert resultado.linha_do_tempo[0].data is None
    assert resultado.linha_do_tempo[0].data_aproximada_texto == "início de março de 2024"
    assert resultado.valores_mencionados[0].valor == 8000.0
    assert len(resultado.lacunas) == 1


def test_data_incerta_nao_vira_data_inventada():
    """Reforça a regra 2 do prompt: se o relato só menciona 'ano passado',
    o schema aceita null em vez de exigir uma data ISO — o mock aqui prova
    que o Pydantic não obriga a IA a inventar uma data."""
    service = ExtracaoFatosService()
    resposta = dict(_RESPOSTA_VALIDA)
    resposta["linha_do_tempo"] = [
        {"data": None, "data_aproximada_texto": "ano passado", "descricao": "Fato ocorrido.", "fonte": "relato"}
    ]
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(resposta))

    entrada = ExtrairFatosRequest(relato="Isso aconteceu ano passado.")
    resultado = service.extrair(entrada)

    assert resultado.linha_do_tempo[0].data is None
    assert resultado.linha_do_tempo[0].data_aproximada_texto == "ano passado"


def test_documentos_ids_sao_informados_ao_modelo_como_indisponiveis():
    service = ExtracaoFatosService()
    mock_create = MagicMock(return_value=_resposta_llm(_RESPOSTA_VALIDA))
    service._client.chat.completions.create = mock_create

    entrada = ExtrairFatosRequest(relato="Relato qualquer.", documentos_ids=["doc-1", "doc-2"])
    service.extrair(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "doc-1" in conteudo_enviado
    assert "doc-2" in conteudo_enviado
    assert "NÃO disponível" in conteudo_enviado


def test_retentativa_quando_json_invalido():
    service = ExtracaoFatosService()
    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[resposta_invalida_msg, _resposta_llm(_RESPOSTA_VALIDA)]
    )

    entrada = ExtrairFatosRequest(relato="Relato qualquer.")
    resultado = service.extrair(entrada)

    assert len(resultado.linha_do_tempo) == 2
    assert service._client.chat.completions.create.call_count == 2


def test_levanta_erro_apos_esgotar_tentativas():
    service = ExtracaoFatosService()
    resposta_invalida = MagicMock(content="ainda inválido")
    service._client.chat.completions.create = MagicMock(
        return_value=MagicMock(choices=[MagicMock(message=resposta_invalida)])
    )

    entrada = ExtrairFatosRequest(relato="Relato qualquer.")
    with pytest.raises(ValueError):
        service.extrair(entrada)


def test_montar_relato_usa_apenas_mensagens_do_usuario():
    from src.domain.schemas import DadosContato, Mensagem, SessaoConversa
    from src.services.extracao_fatos_service import montar_relato_da_sessao

    sessao = SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217"),
        historico=[
            Mensagem(remetente="assistente", texto="Olá! Você concorda em prosseguir?"),
            Mensagem(remetente="usuario", texto="Sim"),
            Mensagem(remetente="assistente", texto="Conte o que aconteceu."),
            Mensagem(remetente="usuario", texto="Fui cobrado indevidamente em R$ 8.000."),
        ],
    )

    relato = montar_relato_da_sessao(sessao)

    assert "Fui cobrado indevidamente" in relato
    assert "Você concorda em prosseguir" not in relato  # fala da assistente não entra
    assert "Conte o que aconteceu" not in relato


def test_extrair_e_persistir_salva_na_sessao_e_no_repositorio(monkeypatch, tmp_path):
    from src.domain.schemas import DadosContato, Mensagem, SessaoConversa
    from src.repositories.session_repository import SessaoRepository
    import src.services.extracao_fatos_service as modulo

    db_path = str(tmp_path / "test.db")
    repo_teste = SessaoRepository(db_path=db_path)
    monkeypatch.setattr(modulo, "sessao_repository", repo_teste)

    sessao = SessaoConversa(
        telefone="5592984705217",
        contato=DadosContato(telefone="5592984705217"),
        historico=[Mensagem(remetente="usuario", texto="Fui cobrado indevidamente em R$ 8.000.")],
    )
    repo_teste.salvar(sessao)

    service = ExtracaoFatosService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(_RESPOSTA_VALIDA))

    resultado = service.extrair_e_persistir(sessao)

    assert sessao.fatos_estruturados is not None
    assert sessao.fatos_estruturados.resumo_narrativo == resultado.resumo_narrativo

    sessao_recarregada = repo_teste.carregar("5592984705217")
    assert sessao_recarregada.fatos_estruturados is not None
    assert sessao_recarregada.fatos_estruturados.resumo_narrativo == resultado.resumo_narrativo