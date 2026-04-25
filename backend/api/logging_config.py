"""
Configuração de logging para a API AncoPlat.

Logger raiz `ancoplat` recebe dois handlers:
  - StreamHandler para console (DEBUG/INFO durante dev).
  - RotatingFileHandler para `backend/data/logs/ancoplat.log` — 5 arquivos
    de até 1 MB cada (5 MB total), com formato estruturado pronto para
    grep/awk.

Loggers principais usados pela aplicação:
  - `ancoplat.api` — middlewares, lifespan, exceções.
  - `ancoplat.api.solve` — uma linha por execução do solver com case_id,
    status, iterações, tempo (ms). Útil para auditoria pós-fato.

A configuração é idempotente: chamar `configure_logging()` mais de uma
vez (por exemplo em testes) não duplica handlers.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from backend.api.config import LOG_FILE, LOG_LEVEL

_CONFIGURED = False


def configure_logging() -> None:
    """Configura logger raiz `ancoplat`. Idempotente."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, LOG_LEVEL, logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger("ancoplat")
    root.setLevel(level)
    # Limpa handlers herdados (evita duplicação em testes/reload).
    root.handlers.clear()
    root.propagate = False  # não escapa para o root global

    # Console
    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # Arquivo rotativo: 1 MB × 5 arquivos
    rotating = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    rotating.setLevel(level)
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
    logger = logging.getLogger("ancoplat.api.solve")
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
