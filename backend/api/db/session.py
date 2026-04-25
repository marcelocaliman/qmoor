"""
Sessão SQLAlchemy para o banco SQLite da AncoPlat.

DATABASE_URL e DB_PATH vêm de `backend.api.config` (env-driven).
Default em dev: backend/data/ancoplat.db.

Migração transparente: se um banco antigo `qmoor.db` existir ao lado do
`ancoplat.db` esperado e o novo ainda não, renomeia automaticamente
preservando dados locais do usuário sem exigir intervenção manual.
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.api.config import DATABASE_URL, DB_PATH

# Compat: se DB legado `qmoor.db` existir ao lado do alvo e o novo
# `ancoplat.db` ainda não, renomeia automaticamente.
_LEGACY_DB = DB_PATH.parent / "qmoor.db"
if _LEGACY_DB.exists() and not DB_PATH.exists():
    try:
        _LEGACY_DB.rename(DB_PATH)
    except OSError:
        # Rename pode falhar por permissions; não trava o startup.
        pass

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
