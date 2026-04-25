"""
Configuração centralizada da API AncoPlat, lida de variáveis de ambiente
ou arquivo `.env` na raiz do projeto.

Todas as constantes têm defaults sensatos para desenvolvimento local
(rodar `uvicorn backend.api.main:app --reload` sem nenhum `.env`
funciona como sempre funcionou). Em produção, `/opt/ancoplat/app/.env`
sobrepõe os defaults.

Variáveis suportadas:
    DATABASE_URL          SQLAlchemy URL. Default: sqlite no dev local.
    LOG_FILE              Caminho do arquivo de log. Default: backend/data/logs/ancoplat.log.
    LOG_LEVEL             INFO|DEBUG|WARNING|ERROR. Default: INFO.
    ENVIRONMENT           "development" | "production". Default: development.
    CORS_ALLOWED_ORIGINS  Lista CSV de origens permitidas. Default: localhost dev.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # python-dotenv ausente — tudo vira default
    load_dotenv = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parents[2]

if load_dotenv is not None:
    # `.env` na raiz do projeto. `override=False`: variáveis já exportadas
    # no shell têm prioridade — útil em CI e em testes que usam monkeypatch.
    load_dotenv(_ROOT / ".env", override=False)


ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


def _sqlite_path_from_url(url: str) -> Path | None:
    """Extrai o path absoluto de uma URL SQLite (sqlite:///rel ou sqlite:////abs)."""
    if url.startswith("sqlite:////"):
        return Path("/" + url[len("sqlite:////") :])
    if url.startswith("sqlite:///"):
        return Path(url[len("sqlite:///") :])
    return None


_default_db_path = _ROOT / "backend" / "data" / "ancoplat.db"
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{_default_db_path}")
DB_PATH: Path = _sqlite_path_from_url(DATABASE_URL) or _default_db_path

_default_log_file = DB_PATH.parent / "logs" / "ancoplat.log"
LOG_FILE: Path = Path(os.getenv("LOG_FILE", str(_default_log_file)))


_default_cors = (
    "http://localhost:5173,http://127.0.0.1:5173,"
    "http://localhost:8000,http://127.0.0.1:8000"
)
CORS_ALLOWED_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", _default_cors).split(",")
    if o.strip()
]


__all__ = [
    "ENVIRONMENT",
    "LOG_LEVEL",
    "DATABASE_URL",
    "DB_PATH",
    "LOG_FILE",
    "CORS_ALLOWED_ORIGINS",
]
