"""
Configuração central de logging da aplicação.

Camada: core.
"""
import logging

from .config import settings


def configurar_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )