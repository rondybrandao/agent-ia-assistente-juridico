"""
Repositório de peças geradas por gerar_peticao.

Camada: repositories. Guardar a peça com um ID é o que permite
revisar_peticao e exportar_documento operarem sobre ela depois, sem
precisar reenviar o texto inteiro a cada chamada.
"""
import sqlite3
from contextlib import contextmanager
from typing import Optional

from ..core.config import settings
from ..domain.peticao_schemas import Peca

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pecas (
    peca_id TEXT PRIMARY KEY,
    dados_json TEXT NOT NULL
);
"""


class PecaRepository:
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

    def salvar(self, peca: Peca) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO pecas (peca_id, dados_json) VALUES (?, ?) "
                "ON CONFLICT(peca_id) DO UPDATE SET dados_json = excluded.dados_json",
                (peca.peca_id, peca.model_dump_json()),
            )

    def buscar(self, peca_id: str) -> Optional[Peca]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT dados_json FROM pecas WHERE peca_id = ?", (peca_id,)
            ).fetchone()
        if row is None:
            return None
        return Peca.model_validate_json(row[0])

    def buscar_mais_recente_por_telefone(self, telefone: str) -> Optional[Peca]:
        """
        Usada pelo chat de pesquisa para responder perguntas sobre "a
        petição em construção" deste caso — sem índice dedicado por
        telefone (a tabela guarda só o JSON), então filtra em memória. Para
        o volume esperado de peças por escritório, isso é suficiente.
        """
        with self._conn() as conn:
            rows = conn.execute("SELECT dados_json FROM pecas").fetchall()
        pecas_do_caso = [
            Peca.model_validate_json(row[0]) for row in rows
        ]
        pecas_do_caso = [p for p in pecas_do_caso if p.telefone == telefone]
        if not pecas_do_caso:
            return None
        return max(pecas_do_caso, key=lambda p: p.criada_em)


# instância padrão usada pela aplicação
peca_repository = PecaRepository()