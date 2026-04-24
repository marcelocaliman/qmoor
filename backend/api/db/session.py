"""
Sessão SQLAlchemy para o banco SQLite da QMoor Web.

Usa o mesmo arquivo de banco que o seed_catalog.py (backend/data/qmoor.db).
Se o banco ainda não existir, a primeira execução do servidor cria o
arquivo vazio e chama as migrations iniciais.
"""
from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Mesma pasta do seed_catalog.py
_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = _ROOT / "backend" / "data" / "qmoor.db"

# check_same_thread=False é necessário para uso concorrente do FastAPI com SQLite.
# SQLite é rápido o suficiente para app local; não há contention real.
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # sem SQL spam no log; habilitar em debug se precisar
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_conn, _) -> None:
    """
    SQLite por default NÃO aplica foreign key constraints. Habilita
    `PRAGMA foreign_keys = ON` em cada nova conexão para que
    ON DELETE CASCADE funcione na relação cases → executions.

    Listener é registrado para TODOS os engines (inclusive os criados em
    tests com DB temporário via conftest). Checa se é SQLite antes de
    emitir o pragma para evitar falhar com outros dialetos no futuro.
    """
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()
    except Exception:  # noqa: BLE001
        # Se não for SQLite (ex: futura migração para PostgreSQL), ignora.
        pass


def get_db() -> Generator[Session, None, None]:
    """Dependência do FastAPI para injetar sessão SQLAlchemy."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "DATABASE_URL", "DB_PATH", "SessionLocal", "engine", "get_db"]
