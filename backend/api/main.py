"""
Entrypoint FastAPI da QMoor Web API.

Sobe uma aplicação ASGI em `localhost:8000` (padrão uvicorn). Sem
autenticação — uso local conforme Seção 1 do docs/plano_F2_api.md.

Como rodar em dev:
    venv/bin/uvicorn backend.api.main:app --reload

Como rodar testes:
    venv/bin/pytest backend/api/tests/
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.db import session as db_session
from backend.api.db.migrations import run_migrations
from backend.api.routers import cases, health
from backend.api.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger("qmoor.api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan: startup aplica migrations idempotentemente; shutdown
    apenas registra. A tabela line_types do seed F1a é preservada.
    """
    del app
    created = run_migrations(db_session.engine)
    if created:
        logger.info("Tabelas criadas no startup: %s", created)
    yield
    logger.debug("Shutdown da API.")


def _create_app() -> FastAPI:
    """Factory: cria e configura a app FastAPI (facilita testes)."""
    app = FastAPI(
        title="QMoor Web API",
        description=(
            "API REST para análise estática de linhas de ancoragem offshore. "
            "Solver de catenária elástica com seabed e atrito de Coulomb, "
            "validado contra MoorPy.\n\n"
            "Uso pessoal/local. Sem autenticação — servidor deve rodar "
            "apenas em localhost."
        ),
        version="0.1.0",
        contact={"name": "Marcelo Caliman"},
        license_info={"name": "Uso pessoal, sem fins comerciais"},
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=_lifespan,
    )

    # CORS restrito a localhost (Vite dev server e acesso direto).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    _register_exception_handlers(app)
    _register_routers(app)
    return app


def _register_routers(app: FastAPI) -> None:
    """Monta todos os routers da API sob /api/v1/."""
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(cases.router, prefix="/api/v1")


def _register_exception_handlers(app: FastAPI) -> None:
    """
    Converte exceções em respostas padronizadas no formato ErrorResponse.

    Nunca vaza stack trace na resposta; logs completos ficam no servidor.
    """

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic validation → 422 padronizado.

        Pydantic 2 coloca a exceção original em `ctx.error` (não-serializável
        para JSON). Convertemos tudo a string antes de devolver ao cliente.
        """
        del request
        safe_errors = []
        for err in exc.errors():
            safe_err = {k: v for k, v in err.items() if k != "ctx"}
            ctx = err.get("ctx")
            if isinstance(ctx, dict):
                safe_err["ctx"] = {k: str(v) for k, v in ctx.items()}
            safe_errors.append(safe_err)
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="validation_error",
                    message="Entrada inválida. Verifique os campos obrigatórios e os tipos.",
                    detail={"errors": safe_errors},
                )
            ).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """HTTPException (404, 409, 503, etc.) → formato ErrorResponse."""
        del request
        # `exc.detail` pode ser string (padrão) ou já um dict estruturado.
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            err = ErrorDetail(**exc.detail)
        else:
            err = ErrorDetail(
                code=f"http_{exc.status_code}",
                message=str(exc.detail) if exc.detail else "Erro HTTP.",
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(error=err).model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Fallback: nunca propaga stack trace para o cliente."""
        logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="internal_server_error",
                    message="Erro interno do servidor. Consulte os logs.",
                )
            ).model_dump(),
        )


app = _create_app()


__all__ = ["app"]
