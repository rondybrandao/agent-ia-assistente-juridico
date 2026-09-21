import time

from src.domain.peticao_schemas import Peca
from src.repositories.peca_repository import PecaRepository


def _criar_repo(tmp_path) -> PecaRepository:
    return PecaRepository(db_path=str(tmp_path / "test.db"))


def test_buscar_por_id_apos_salvar(tmp_path):
    repo = _criar_repo(tmp_path)
    peca = Peca(peca_id="p1", telefone="5592984705217", template_id="x", titulo="Título", peca_texto="texto")
    repo.salvar(peca)

    encontrada = repo.buscar("p1")
    assert encontrada is not None
    assert encontrada.titulo == "Título"


def test_buscar_por_id_inexistente_retorna_none(tmp_path):
    repo = _criar_repo(tmp_path)
    assert repo.buscar("nao-existe") is None


def test_buscar_mais_recente_por_telefone(tmp_path):
    repo = _criar_repo(tmp_path)
    repo.salvar(Peca(peca_id="p1", telefone="5592984705217", template_id="x", titulo="Peça antiga", peca_texto="..."))
    time.sleep(0.01)
    repo.salvar(Peca(peca_id="p2", telefone="5592984705217", template_id="x", titulo="Peça nova", peca_texto="..."))

    mais_recente = repo.buscar_mais_recente_por_telefone("5592984705217")
    assert mais_recente is not None
    assert mais_recente.titulo == "Peça nova"


def test_buscar_mais_recente_por_telefone_ignora_outros_casos(tmp_path):
    repo = _criar_repo(tmp_path)
    repo.salvar(Peca(peca_id="p1", telefone="5592984705217", template_id="x", titulo="Caso A", peca_texto="..."))
    repo.salvar(Peca(peca_id="p2", telefone="5511999999999", template_id="x", titulo="Caso B", peca_texto="..."))

    resultado = repo.buscar_mais_recente_por_telefone("5511999999999")
    assert resultado.titulo == "Caso B"


def test_buscar_mais_recente_por_telefone_sem_pecas_retorna_none(tmp_path):
    repo = _criar_repo(tmp_path)
    assert repo.buscar_mais_recente_por_telefone("5592984705217") is None


def test_peca_sem_telefone_nao_aparece_na_busca_por_telefone(tmp_path):
    """Peças geradas sem telefone (ex.: chamada avulsa da API sem
    contexto de caso) não devem quebrar nem aparecer na busca."""
    repo = _criar_repo(tmp_path)
    repo.salvar(Peca(peca_id="p1", telefone=None, template_id="x", titulo="Avulsa", peca_texto="..."))

    assert repo.buscar_mais_recente_por_telefone("5592984705217") is None
