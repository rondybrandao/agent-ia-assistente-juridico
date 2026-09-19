"""
Entrypoint da aplicação.

Roda com:
    uvicorn src.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.casos_routes import router as casos_router
from .api.citacoes_routes import router as citacoes_router
from .api.webhook_routes import router as webhook_router
from .core.logging import configurar_logging


def criar_app() -> FastAPI:
    configurar_logging()
    app = FastAPI(title="Assistente de Triagem Jurídica")

    # Necessário para o frontend Angular (rodando em outra porta, ex: 4200)
    # conseguir chamar esta API durante o desenvolvimento.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(webhook_router)
    app.include_router(casos_router)
    app.include_router(citacoes_router)
    return app


app = criar_app()