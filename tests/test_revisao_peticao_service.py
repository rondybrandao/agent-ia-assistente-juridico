import json
from unittest.mock import MagicMock

import pytest

from src.domain.peticao_schemas import CitacaoParaPeca, Peca
from src.domain.revisao_schemas import ChecklistDisponivel, StatusItemChecklist
from src.repositories.peca_repository import PecaRepository
from src.services import revisao_peticao_service as revisao_module
from src.services.revisao_peticao_service import RevisaoPeticaoService


def _resposta_llm(itens: list):
    msg = MagicMock(content=json.dumps({"itens": itens}, ensure_ascii=False))
    return MagicMock(choices=[MagicMock(message=msg)])


def _criar_peca(peca_texto: str, citacoes_utilizadas=None) -> Peca:
    return Peca(
        peca_id="peca-teste-1",
        template_id="consumo_indenizatoria_jec",
        titulo="Ação de consumo",
        peca_texto=peca_texto,
        citacoes_utilizadas=citacoes_utilizadas or [],
    )


@pytest.mark.asyncio
async def test_peca_sem_pendente_e_checklist_completo_fica_ok(monkeypatch, tmp_path):
    repo = PecaRepository(db_path=str(tmp_path / "test.db"))
    repo.salvar(_criar_peca("Texto completo da peça, sem pendências."))
    monkeypatch.setattr(revisao_module, "peca_repository", repo)

    itens_ok = [
        {"item": item, "status": "ok", "observacao": "Presente."}
        for item in revisao_module._CHECKLISTS["jec_lei_9099"]
    ]
    service = RevisaoPeticaoService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(itens_ok))

    resultado = await service.revisar("peca-teste-1", ChecklistDisponivel.JEC_LEI_9099)

    assert resultado.tem_pendencia is False
    assert all(i.status == StatusItemChecklist.OK for i in resultado.itens)


@pytest.mark.asyncio
async def test_campo_pendente_no_texto_e_detectado_sem_depender_do_llm(monkeypatch, tmp_path):
    """A checagem de [PENDENTE] é feita em código Python, não pelo LLM —
    então mesmo se o LLM disser que está tudo ok, esse item específico
    deve continuar aparecendo como 'faltando'."""
    repo = PecaRepository(db_path=str(tmp_path / "test.db"))
    repo.salvar(_criar_peca("Réu: [PENDENTE: endereço do réu]. Resto do texto."))
    monkeypatch.setattr(revisao_module, "peca_repository", repo)

    itens_ok_segundo_llm = [
        {"item": item, "status": "ok", "observacao": "Presente."}
        for item in revisao_module._CHECKLISTS["jec_lei_9099"]
    ]
    service = RevisaoPeticaoService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(itens_ok_segundo_llm))

    resultado = await service.revisar("peca-teste-1", ChecklistDisponivel.JEC_LEI_9099)

    item_pendencia = resultado.itens[0]
    assert "PENDENTE" in item_pendencia.item or "pendente" in item_pendencia.observacao.lower()
    assert item_pendencia.status == StatusItemChecklist.FALTANDO
    assert resultado.tem_pendencia is True


@pytest.mark.asyncio
async def test_peca_inexistente_levanta_erro(monkeypatch, tmp_path):
    repo = PecaRepository(db_path=str(tmp_path / "test.db"))
    monkeypatch.setattr(revisao_module, "peca_repository", repo)

    service = RevisaoPeticaoService()
    with pytest.raises(ValueError):
        await service.revisar("nao-existe", ChecklistDisponivel.CPC_319)


@pytest.mark.asyncio
async def test_checklist_cpc_319_tem_os_itens_esperados(monkeypatch, tmp_path):
    repo = PecaRepository(db_path=str(tmp_path / "test.db"))
    repo.salvar(_criar_peca("Peça qualquer."))
    monkeypatch.setattr(revisao_module, "peca_repository", repo)

    itens_llm = [
        {"item": item, "status": "ok", "observacao": "-"}
        for item in revisao_module._CHECKLISTS["cpc_319"]
    ]
    service = RevisaoPeticaoService()
    service._client.chat.completions.create = MagicMock(return_value=_resposta_llm(itens_llm))

    resultado = await service.revisar("peca-teste-1", ChecklistDisponivel.CPC_319)

    textos_itens = [i.item for i in resultado.itens]
    assert any("valor da causa" in t.lower() for t in textos_itens)
    assert any("art. 320" in t for t in textos_itens)  # documentos indispensáveis


@pytest.mark.asyncio
async def test_retentativa_quando_llm_devolve_json_invalido(monkeypatch, tmp_path):
    repo = PecaRepository(db_path=str(tmp_path / "test.db"))
    repo.salvar(_criar_peca("Texto sem pendências."))
    monkeypatch.setattr(revisao_module, "peca_repository", repo)

    resposta_invalida = MagicMock(content="não é json")
    resposta_invalida_msg = MagicMock(choices=[MagicMock(message=resposta_invalida)])

    itens_validos = [{"item": "x", "status": "ok", "observacao": "-"}]
    service = RevisaoPeticaoService()
    service._client.chat.completions.create = MagicMock(
        side_effect=[resposta_invalida_msg, _resposta_llm(itens_validos)]
    )

    resultado = await service.revisar("peca-teste-1", ChecklistDisponivel.CPC_319)

    assert service._client.chat.completions.create.call_count == 2
    assert resultado.peca_id == "peca-teste-1"
