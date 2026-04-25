"""
Configuração de logging para a API QMoor Web.

Logger raiz `qmoor` recebe dois handlers:
  - StreamHandler para console (DEBUG/INFO durante dev).
  - RotatingFileHandler para `backend/data/logs/qmoor.log` — 5 arquivos
    de até 1 MB cada (5 MB total), com formato estruturado pronto para
    grep/awk.

Loggers principais usados pela aplicação:
  - `qmoor.api` — middlewares, lifespan, exceções.
  - `qmoor.api.solve` — uma linha por execução do solver com case_id,
    status, iterações, tempo (ms). Útil para auditoria pós-fato.

A configuração é idempotente: chamar `configure_logging()` mais de uma
vez (por exemplo em testes) não duplica handlers.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.api.db.session import DB_PATH

_CONFIGURED = False


def configure_logging() -> None:
    """Configura logger raiz `qmoor`. Idempotente."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(DB_PATH).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "qmoor.log"

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger("qmoor")
    root.setLevel(logging.INFO)
    # Limpa handlers herdados (evita duplicação em testes/reload).
    root.handlers.clear()
    root.propagate = False  # não escapa para o root global

    # Console
    stream = logging.StreamHandler()
    stream.setLevel(logging.INFO)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # Arquivo rotativo: 1 MB × 5 arquivos
    rotating = RotatingFileHandler(
        log_file,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    rotating.setLevel(logging.INFO)
    rotating.setFormatter(fmt)
    root.addHandler(rotating)

    _CONFIGURED = True


def log_solver_execution(
    *,
    case_id: int,
    status: str,
    iterations: int,
    elapsed_ms: float,
    alert_level: str | None = None,
    message: str | None = None,
) -> None:
    """
    Log estruturado de uma execução do solver.

    Formato fixo, em uma única linha, fácil de grep:
        case_id=123 status=converged alert=ok iterations=14 elapsed_ms=42.3
    """
    logger = logging.getLogger("qmoor.api.solve")
    parts = [
        f"case_id={case_id}",
        f"status={status}",
        f"alert={alert_level or '-'}",
        f"iterations={iterations}",
        f"elapsed_ms={elapsed_ms:.1f}",
    ]
    if message:
        # Mensagens podem ter newlines/aspas; normaliza para single line.
        single = message.replace("\n", " | ").replace('"', "'")
        parts.append(f'msg="{single[:200]}"')
    logger.info(" ".join(parts))


__all__ = ["configure_logging", "log_solver_execution"]
