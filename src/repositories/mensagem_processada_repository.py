"""
Controle de deduplicação de mensagens do WhatsApp.

Camada: repositories. A Meta pode reenviar o mesmo webhook várias vezes se
a resposta demorar; este repositório guarda os IDs de mensagem já
processados para que reenvios sejam identificados e ignorados, evitando
respostas duplicadas ao usuário.
"""
import sqlite3
import time
from contextlib import contextmanager

from ..core.config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mensagens_processadas (
    message_id TEXT PRIMARY KEY,
    processada_em REAL NOT NULL
);
"""


class MensagemProcessadaRepository:
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

    def ja_processada(self, message_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM mensagens_processadas WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return row is not None

    def marcar_processada(self, message_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mensagens_processadas (message_id, processada_em) "
                "VALUES (?, ?)",
                (message_id, time.time()),
            )


# instância padrão usada pela aplicação
mensagem_processada_repository = MensagemProcessadaRepository()
