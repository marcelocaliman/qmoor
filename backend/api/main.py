"""
Entrypoint FastAPI da AncoPlat API.

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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.config import CORS_ALLOWED_ORIGINS
from backend.api.db import session as db_session
from backend.api.db.migrations import run_migrations
from backend.api.logging_config import configure_logging
from backend.api.routers import (
    cases,
    health,
    line_types,
    moor_io,
    mooring_systems,
    reports,
    solve,
)
from backend.api.schemas.errors import ErrorDetail, ErrorResponse

# Logging estruturado: console + arquivo rotativo. Configurado uma única
# vez no import do módulo (idempotente).
configure_logging()
logger = logging.getLogger("ancoplat.api")

# Rate limit global: 100 req/min por IP. Mesmo em localhost a barreira é
# útil para detectar loops acidentais (ex.: useEffect mal configurado no
# frontend) sem precisar tirar o servidor do ar.
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


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


TAGS_METADATA = [
    {
        "name": "metadata",
        "description": (
            "Healthcheck, versão e perfis de critério de utilização. "
            "Úteis para integração com UI e monitoring local."
        ),
    },
    {
        "name": "cases",
        "description": (
            "CRUD de casos de ancoragem. Um caso guarda o input do solver "
            "(segmentos, boundary, seabed, perfil de critério) e o histórico "
            "das últimas 10 execuções."
        ),
    },
    {
        "name": "solve",
        "description": (
            "Execução do solver de catenária em um caso salvo. "
            "Persiste o resultado e retorna SolverResult completo."
        ),
    },
    {
        "name": "catalog",
        "description": (
            "Catálogo de tipos de linha (522 entradas legacy_qmoor "
            "em SI, imutáveis). Entradas `user_input` podem ser criadas, "
            "editadas e removidas livremente."
        ),
    },
    {
        "name": "import-export",
        "description": (
            "Importação de casos a partir de JSON `.moor` "
            "(schema Seção 5.2 do MVP v2) e exportação em três formatos: "
            "`.moor` (JSON), JSON normalizado e PDF técnico."
        ),
    },
    {
        "name": "mooring-systems",
        "description": (
            "Sistemas de ancoragem multi-linha (F5.4). Cada sistema "
            "contém N linhas com posição polar (azimuth + raio) no "
            "frame do casco. O solver resolve cada linha "
            "independentemente e agrega o resultante horizontal."
        ),
    },
]


def _create_app() -> FastAPI:
    """Factory: cria e configura a app FastAPI (facilita testes)."""
    app = FastAPI(
        title="AncoPlat API",
        description=(
            "API REST para análise estática de linhas de ancoragem offshore.\n\n"
            "Solver de **catenária elástica** com contato com seabed e "
            "atrito de Coulomb, validado contra [MoorPy](https://github.com/NREL/MoorPy) "
            "em 9 casos de benchmark (BC-01..BC-09) com desvio < 1% em força "
            "e < 0,5% em geometria.\n\n"
            "**Uso pessoal/local.** Servidor roda em `localhost:8000` sem "
            "autenticação — firewall do macOS é a barreira.\n\n"
            "Unidades **internas em SI** (m, N, Pa, N/m). Conversões "
            "para imperial/metric acontecem nas bordas (`.moor` import/export, UI)."
        ),
        version="0.1.0",
        contact={"name": "Marcelo Caliman"},
        license_info={"name": "Uso pessoal, sem fins comerciais"},
        openapi_tags=TAGS_METADATA,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
        lifespan=_lifespan,
    )

    # CORS: lista vinda de config (env-driven). Default = localhost dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Rate limit middleware: aplica o `default_limits` do `limiter` em todas
    # as rotas. Endpoints individuais podem sobrescrever via decorator.
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    _register_exception_handlers(app)
    _register_routers(app)
    return app


def _register_routers(app: FastAPI) -> None:
    """Monta todos os routers da API sob /api/v1/."""
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(cases.router, prefix="/api/v1")
    app.include_router(solve.router, prefix="/api/v1")
    app.include_router(line_types.router, prefix="/api/v1")
    app.include_router(moor_io.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(mooring_systems.router, prefix="/api/v1")


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
