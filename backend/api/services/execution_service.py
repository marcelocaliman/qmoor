"""
Lógica de execução do solver para um caso (F2.4).

Hidrata o CaseInput persistido, invoca solve(), persiste ExecutionRecord,
e aplica a política de retenção (10 mais recentes por caso).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.db.models import CaseRecord, ExecutionRecord
from backend.api.logging_config import log_solver_execution
from backend.api.schemas.cases import CaseInput
from backend.api.services.case_service import CaseNotFound, get_case
from backend.solver.solver import solve as solver_solve
from backend.solver.types import ConvergenceStatus, SolverResult

logger = logging.getLogger("qmoor.api.execution")

# Número máximo de execuções mantidas por caso
RETENTION_LIMIT = 10


def run_solve_and_persist(
    db: Session, case_id: int
) -> tuple[ExecutionRecord, SolverResult]:
    """
    Resolve o caso `case_id` e persiste a execução.

    Retorna (execution_record, solver_result).
    Levanta CaseNotFound se o id não existe.
    """
    rec = get_case(db, case_id)  # CaseNotFound propaga
    case_input = CaseInput.model_validate_json(rec.input_json)

    # Invoca o solver (nunca crasha — sempre retorna SolverResult).
    # Cronometra para o log estruturado de auditoria.
    t0 = time.perf_counter()
    result = solver_solve(
        line_segments=case_input.segments,
        boundary=case_input.boundary,
        seabed=case_input.seabed,
        criteria_profile=case_input.criteria_profile,
        user_limits=case_input.user_defined_limits,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    exec_rec = ExecutionRecord(
        case_id=case_id,
        result_json=result.model_dump_json(),
        status=result.status.value,
        alert_level=result.alert_level.value,
        fairlead_tension=result.fairlead_tension if result.fairlead_tension else None,
        total_horz_distance=(
            result.total_horz_distance if result.total_horz_distance else None
        ),
        utilization=result.utilization if result.utilization else None,
    )
    db.add(exec_rec)
    db.commit()
    db.refresh(exec_rec)

    # Log estruturado em arquivo rotativo + console (para grep/awk pós-fato).
    log_solver_execution(
        case_id=case_id,
        status=result.status.value,
        iterations=result.iterations_used,
        elapsed_ms=elapsed_ms,
        alert_level=result.alert_level.value,
        message=result.message,
    )

    _enforce_retention(db, case_id)
    return exec_rec, result


def _enforce_retention(db: Session, case_id: int) -> int:
    """
    Mantém apenas as RETENTION_LIMIT execuções mais recentes do caso.
    Retorna o número de linhas removidas.
    """
    stmt = (
        select(ExecutionRecord.id)
        .where(ExecutionRecord.case_id == case_id)
        .order_by(ExecutionRecord.executed_at.desc(), ExecutionRecord.id.desc())
        .offset(RETENTION_LIMIT)
    )
    old_ids = db.execute(stmt).scalars().all()
    if not old_ids:
        return 0
    count = 0
    for old_id in old_ids:
        old = db.get(ExecutionRecord, old_id)
        if old is not None:
            db.delete(old)
            count += 1
    if count:
        db.commit()
    return count


def http_status_for_solver_status(status: ConvergenceStatus) -> int:
    """
    Mapeia ConvergenceStatus → HTTP status (Seção 5.3 do plano F2):
      converged/ill_conditioned → 200 (usável, ill_conditioned com aviso)
      max_iterations            → 200 (parcial, com aviso no body)
      invalid_case/numerical_error → 422 (input inviável)
    """
    if status in (ConvergenceStatus.CONVERGED, ConvergenceStatus.ILL_CONDITIONED):
        return 200
    if status == ConvergenceStatus.MAX_ITERATIONS:
        return 200
    # invalid_case, numerical_error
    return 422


__all__ = [
    "RETENTION_LIMIT",
    "http_status_for_solver_status",
    "run_solve_and_persist",
]
