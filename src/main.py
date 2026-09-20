"""
Entrypoint da aplicação.

Roda com:
    uvicorn src.main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.casos_routes import router as casos_router
from .api.citacoes_routes import router as citacoes_router
from .api.classificacao_routes import router as classificacao_router
from .api.competencia_routes import router as competencia_router
from .api.custas_routes import router as custas_router
from .api.fatos_routes import router as fatos_router
from .api.peticoes_routes import router as peticoes_router
from .api.prazos_routes import router as prazos_router
from .api.pressupostos_routes import router as pressupostos_router
from .api.valor_causa_routes import router as valor_causa_router
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
    app.include_router(peticoes_router)
    app.include_router(competencia_router)
    app.include_router(pressupostos_router)
    app.include_router(classificacao_router)
    app.include_router(prazos_router)
    app.include_router(fatos_router)
    app.include_router(valor_causa_router)
    app.include_router(custas_router)
    return app


app = criar_app()