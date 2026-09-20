import json
from unittest.mock import MagicMock

import pytest

from src.domain.peca_acessoria_schemas import PecaAcessoriaRequest
from src.services.peca_acessoria_service import PecaAcessoriaService


def _resposta_llm(conteudo: dict):
    msg = MagicMock(content=json.dumps(conteudo, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def test_listar_templates_retorna_as_4_pecas_acessorias():
    service = PecaAcessoriaService()
    templates = service.listar_templates()
    assert len(templates) == 4
    ids = {t["template_id"] for t in templates}
    assert ids == {
        "procuracao_ad_judicia",
        "declaracao_hipossuficiencia",
        "notificacao_extrajudicial",
        "rol_documentos",
    }


def test_buscar_template_inexistente_levanta_erro():
    service = PecaAcessoriaService()
    with pytest.raises(ValueError):
        service.buscar_template("nao_existe")


@pytest.mark.asyncio
async def test_gerar_procuracao_com_resposta_valida():
    service = PecaAcessoriaService()
    service._client.chat.completions.create = MagicMock(
        return_value=_resposta_llm(
            {
                "peca_texto": "PROCURAÇÃO AD JUDICIA (texto completo preenchido)",
                "campos_pendentes": [],
            }
        )
    )

    entrada = PecaAcessoriaRequest(
        template_id="procuracao_ad_judicia",
        dados={"nome_advogado": "Dra. Fulana", "uf": "AM", "numero": "12345"},
    )
    resultado = await service.gerar(entrada)

    assert resultado.template_id == "procuracao_ad_judicia"
    assert resultado.titulo == "Procuração Ad Judicia"
    assert "PROCURAÇÃO AD JUDICIA" in resultado.peca_texto


@pytest.mark.asyncio
async def test_esqueleto_enviado_ao_modelo_ja_tem_qualificacao_pf_expandida():
    """O bloco {{bloco:qualificacao_pf}} deve ser expandido em código antes
    de chegar no modelo — não pode sobrar como {{bloco:...}} literal."""
    service = PecaAcessoriaService()
    mock_create = MagicMock(return_value=_resposta_llm({"peca_texto": "...", "campos_pendentes": []}))
    service._client.chat.completions.create = mock_create

    entrada = PecaAcessoriaRequest(template_id="procuracao_ad_judicia", dados={})
    await service.gerar(entrada)

    conteudo_enviado = mock_create.call_args.kwargs["messages"][1]["content"]
    assert "{{bloco:" not in conteudo_enviado
    assert "{{cpf}}" in conteudo_enviado  # placeholder normal, não é bloco


@pytest.mark.asyncio
async def test_gerar_com_template_inexistente_levanta_erro():
    service = PecaAcessoriaService()
    entrada = PecaAcessoriaRequest(template_id="nao_existe", dados={})
    with pytest.raises(ValueError):
        await service.gerar(entrada)


@pytest.mark.asyncio
async def test_retentativa_quando_json_invalido():
    service = PecaAcessoriaService()
    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    service._client.chat.completions.create = MagicMock(
        side_effect=[
            resposta_invalida_msg,
            _resposta_llm({"peca_texto": "corrigido", "campos_pendentes": []}),
        ]
    )

    entrada = PecaAcessoriaRequest(template_id="declaracao_hipossuficiencia", dados={"nome": "João", "cpf": "123"})
    resultado = await service.gerar(entrada)

    assert resultado.peca_texto == "corrigido"
    assert service._client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_peca_acessoria_fica_persistida_e_recuperavel(tmp_path):
    from src.repositories.peca_repository import PecaRepository

    db_path = str(tmp_path / "test.db")
    repo_teste = PecaRepository(db_path=db_path)

    import src.services.peca_acessoria_service as modulo

    original_repo = modulo.peca_repository
    modulo.peca_repository = repo_teste
    try:
        service = PecaAcessoriaService()
        service._client.chat.completions.create = MagicMock(
            return_value=_resposta_llm({"peca_texto": "rol de documentos gerado", "campos_pendentes": []})
        )
        entrada = PecaAcessoriaRequest(
            template_id="rol_documentos",
            dados={"documentos": [{"descricao": "RG", "data": "2024-01-01", "finalidade": "identificação"}]},
        )
        resultado = await service.gerar(entrada)

        peca_salva = repo_teste.buscar(resultado.peca_id)
        assert peca_salva is not None
        assert peca_salva.peca_texto == "rol de documentos gerado"
    finally:
        modulo.peca_repository = original_repo
