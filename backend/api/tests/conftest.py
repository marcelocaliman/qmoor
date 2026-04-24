"""Fixtures de teste para a API QMoor Web."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.db import session as db_session_module
from backend.api.db.migrations import run_migrations
from backend.api.main import app


@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """
    Isola cada teste em um banco SQLite temporário.

    Faz monkey-patch no engine/SessionLocal do módulo db.session para
    apontar para `tmp_path/qmoor_test.db`. A dependency get_db continua
    funcionando pois lê SessionLocal dinamicamente.
    """
    db_path = tmp_path / "qmoor_test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(db_session_module, "engine", engine)
    monkeypatch.setattr(db_session_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(db_session_module, "DB_PATH", db_path)

    # Aplica migrations no banco temporário (cria cases/executions/app_config).
    # line_types não é criada aqui — testes que precisam do catálogo devem
    # usar a fixture `seeded_catalog` (a ser adicionada em F2.5).
    run_migrations(engine)

    yield db_path

    engine.dispose()


@pytest.fixture()
def client(tmp_db: Path) -> Iterator[TestClient]:
    """TestClient do FastAPI com banco temporário já configurado."""
    del tmp_db
    with TestClient(app) as c:
        yield c
