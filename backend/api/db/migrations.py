"""
Migrations iniciais (F2.2).

Estratégia: DROP+CREATE não é seguro depois que `line_types` tem 522
entradas reais. Usamos `Base.metadata.create_all()` que é idempotente
(cria apenas tabelas que ainda não existem).

Para o MVP pessoal isso basta. Alembic fica para F3+ conforme Seção
10 do plano F2.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

# Importa todos os modelos para registrar no Base.metadata.
from backend.api.db import models  # noqa: F401  (side-effect: registra modelos)
from backend.api.db.session import Base

logger = logging.getLogger("qmoor.api.migrations")


def run_migrations(engine: Engine) -> list[str]:
    """
    Aplica migrations idempotentemente. Retorna a lista de tabelas criadas
    nesta chamada (vazia se já estava tudo criado).
    """
    inspector = inspect(engine)
    before = set(inspector.get_table_names())
    Base.metadata.create_all(bind=engine, checkfirst=True)
    # Refresca para ver o que foi criado nesta chamada
    inspector = inspect(engine)
    after = set(inspector.get_table_names())
    created = sorted(after - before)
    if created:
        logger.info("Migrations aplicadas: %s", ", ".join(created))
    else:
        logger.debug("Nenhuma migration aplicada (schema já atualizado).")
    return created


__all__ = ["run_migrations"]
