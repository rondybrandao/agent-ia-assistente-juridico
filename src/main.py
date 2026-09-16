"""
Entrypoint da aplicação.

Roda com:
    uvicorn src.main:app --reload --port 8000
"""
from fastapi import FastAPI

from .api.webhook_routes import router as webhook_router
from .core.logging import configurar_logging


def criar_app() -> FastAPI:
    configurar_logging()
    app = FastAPI(title="Assistente de Triagem Jurídica")
    app.include_router(webhook_router)
    return app


app = criar_app()