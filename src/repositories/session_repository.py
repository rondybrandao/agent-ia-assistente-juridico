"""
Repositório de sessões de conversa.

Camada: repositories — único lugar do projeto que sabe como os dados são
persistidos. Hoje é SQLite; trocar por Postgres/Redis significa reescrever
só este arquivo, sem tocar em domain, services ou api.
"""
import sqlite3
from contextlib import contextmanager
from typing import Optional

from ..core.config import settings
from ..domain.schemas import DadosContato, SessaoConversa

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessoes (
    telefone TEXT PRIMARY KEY,
    dados_json TEXT NOT NULL
);
"""


class SessaoRepository:
    def __init__(self, db_path: str = settings.DB_PATH) -> None:
        self._db_path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)

    def carregar(self, telefone: str) -> Optional[SessaoConversa]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT dados_json FROM sessoes WHERE telefone = ?", (telefone,)
            ).fetchone()
        if row is None:
            return None
        return SessaoConversa.model_validate_json(row[0])

    def salvar(self, sessao: SessaoConversa) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO sessoes (telefone, dados_json) VALUES (?, ?) "
                "ON CONFLICT(telefone) DO UPDATE SET dados_json = excluded.dados_json",
                (sessao.telefone, sessao.model_dump_json()),
            )

    def obter_ou_criar(self, telefone: str) -> SessaoConversa:
        sessao = self.carregar(telefone)
        if sessao is None:
            sessao = SessaoConversa(telefone=telefone, contato=DadosContato(telefone=telefone))
            self.salvar(sessao)
        return sessao

    def listar_todas(self) -> list[SessaoConversa]:
        """Usado pelo modo advogado para listar os casos existentes."""
        with self._conn() as conn:
            rows = conn.execute("SELECT dados_json FROM sessoes").fetchall()
        return [SessaoConversa.model_validate_json(row[0]) for row in rows]


# instância padrão usada pela aplicação (injeção simples para o protótipo)
sessao_repository = SessaoRepository()