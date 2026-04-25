"""
Lógica de negócio para mooring systems (F5.4.1 — CRUD).

Mesma estratégia adotada em `case_service`: o input completo
(`MooringSystemInput`) vai para `config_json` e os campos
desnormalizados vivem em colunas próprias para queries rápidas. A
execução do solver multi-linha + agregação de forças entra na F5.4.2.
"""
from __future__ import annotations

import logging
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.db.models import (
    MooringSystemExecutionRecord,
    MooringSystemRecord,
)
from backend.api.schemas.mooring_systems import (
    MooringSystemExecutionOutput,
    MooringSystemInput,
    MooringSystemOutput,
    MooringSystemSummary,
)
from backend.solver.equilibrium import solve_platform_equilibrium
from backend.solver.multi_line import solve_mooring_system as solve_msys
from backend.solver.types import (
    EnvironmentalLoad,
    MooringSystemResult,
    PlatformEquilibriumResult,
)


# Política de retenção de execuções (mesmo número de cases.executions).
EXECUTION_RETENTION = 10

logger = logging.getLogger("qmoor.api.mooring_systems")


# ==============================================================================
# Conversões record ↔ schemas
# ==============================================================================


def mooring_system_record_to_summary(
    rec: MooringSystemRecord,
) -> MooringSystemSummary:
    return MooringSystemSummary(
        id=rec.id,
        name=rec.name,
        description=rec.description,
        platform_radius=rec.platform_radius,
        line_count=rec.line_count,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def mooring_system_record_to_output(
    rec: MooringSystemRecord,
) -> MooringSystemOutput:
    config = MooringSystemInput.model_validate_json(rec.config_json)
    executions: list[MooringSystemExecutionOutput] = []
    for e in rec.executions:
        try:
            executions.append(
                MooringSystemExecutionOutput(
                    id=e.id,
                    mooring_system_id=e.mooring_system_id,
                    result=MooringSystemResult.model_validate_json(e.result_json),
                    executed_at=e.executed_at,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "execução id=%s do mooring system id=%s ignorada "
                "(result_json corrompido): %s",
                e.id, rec.id, exc,
            )
    return MooringSystemOutput(
        id=rec.id,
        name=rec.name,
        description=rec.description,
        input=config,
        latest_executions=executions,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


# ==============================================================================
# CRUD
# ==============================================================================


def create_mooring_system(
    db: Session, msys_input: MooringSystemInput
) -> MooringSystemRecord:
    """Persiste um novo mooring system. Retorna o record criado já hidratado."""
    rec = MooringSystemRecord(
        name=msys_input.name,
        description=msys_input.description,
        platform_radius=msys_input.platform_radius,
        line_count=len(msys_input.lines),
        config_json=msys_input.model_dump_json(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    logger.info(
        "Mooring system criado: id=%s name=%r line_count=%d",
        rec.id, rec.name, rec.line_count,
    )
    return rec


def get_mooring_system(db: Session, msys_id: int) -> MooringSystemRecord | None:
    return db.get(MooringSystemRecord, msys_id)


def list_mooring_systems(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
) -> tuple[Sequence[MooringSystemRecord], int]:
    """Lista paginada com filtro opcional por substring no nome."""
    stmt = select(MooringSystemRecord)
    count_stmt = select(func.count()).select_from(MooringSystemRecord)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(MooringSystemRecord.name.ilike(like))
        count_stmt = count_stmt.where(MooringSystemRecord.name.ilike(like))
    stmt = stmt.order_by(MooringSystemRecord.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    items = db.scalars(stmt).all()
    total = db.scalar(count_stmt) or 0
    return items, total


def update_mooring_system(
    db: Session,
    msys_id: int,
    msys_input: MooringSystemInput,
) -> MooringSystemRecord | None:
    """Atualiza completamente. Retorna None se não existir."""
    rec = db.get(MooringSystemRecord, msys_id)
    if rec is None:
        return None
    rec.name = msys_input.name
    rec.description = msys_input.description
    rec.platform_radius = msys_input.platform_radius
    rec.line_count = len(msys_input.lines)
    rec.config_json = msys_input.model_dump_json()
    db.commit()
    db.refresh(rec)
    logger.info(
        "Mooring system atualizado: id=%s name=%r line_count=%d",
        rec.id, rec.name, rec.line_count,
    )
    return rec


def delete_mooring_system(db: Session, msys_id: int) -> bool:
    rec = db.get(MooringSystemRecord, msys_id)
    if rec is None:
        return False
    db.delete(rec)
    db.commit()
    logger.info("Mooring system deletado: id=%s", msys_id)
    return True


# ==============================================================================
# Solve + persistência de execuções
# ==============================================================================


def _prune_old_executions(db: Session, msys_id: int) -> int:
    """
    Mantém só as `EXECUTION_RETENTION` execuções mais recentes do
    mooring system. Retorna a quantidade removida.
    """
    keep_ids = db.scalars(
        select(MooringSystemExecutionRecord.id)
        .where(MooringSystemExecutionRecord.mooring_system_id == msys_id)
        .order_by(MooringSystemExecutionRecord.executed_at.desc())
        .limit(EXECUTION_RETENTION)
    ).all()
    if not keep_ids:
        return 0
    delete_q = (
        select(MooringSystemExecutionRecord)
        .where(MooringSystemExecutionRecord.mooring_system_id == msys_id)
        .where(MooringSystemExecutionRecord.id.notin_(keep_ids))
    )
    to_remove = db.scalars(delete_q).all()
    for rec in to_remove:
        db.delete(rec)
    if to_remove:
        db.commit()
    return len(to_remove)


def solve_and_persist(
    db: Session, msys_id: int
) -> tuple[MooringSystemRecord, MooringSystemExecutionRecord] | None:
    """
    Resolve um mooring system existente, persiste a execução e aplica
    retenção de 10. Retorna (record do sistema, record da execução) ou
    None se o sistema não existir.

    A solver `solve_mooring_system` nunca lança — linhas que falham
    aparecem com status diferente de CONVERGED dentro do resultado, mas
    a execução é persistida normalmente. O decisão é por reportar o
    resultado parcial em vez de descartar tudo.
    """
    rec = db.get(MooringSystemRecord, msys_id)
    if rec is None:
        return None

    msys_input = MooringSystemInput.model_validate_json(rec.config_json)
    result = solve_msys(msys_input)

    exec_rec = MooringSystemExecutionRecord(
        mooring_system_id=msys_id,
        result_json=result.model_dump_json(),
        aggregate_force_magnitude=result.aggregate_force_magnitude,
        aggregate_force_azimuth_deg=result.aggregate_force_azimuth_deg,
        max_utilization=result.max_utilization,
        worst_alert_level=result.worst_alert_level.value,
        n_converged=result.n_converged,
        n_invalid=result.n_invalid,
    )
    db.add(exec_rec)
    db.commit()
    db.refresh(exec_rec)

    pruned = _prune_old_executions(db, msys_id)
    if pruned:
        logger.info(
            "Mooring system id=%s: %d execução(ões) antigas removidas (retenção %d).",
            msys_id, pruned, EXECUTION_RETENTION,
        )

    db.refresh(rec)
    logger.info(
        "Mooring system resolvido: id=%s name=%r mag=%.1f kN converged=%d/%d alert=%s",
        rec.id, rec.name, result.aggregate_force_magnitude / 1000.0,
        result.n_converged, len(result.lines), result.worst_alert_level.value,
    )
    return rec, exec_rec


def preview_solve(msys_input: MooringSystemInput) -> MooringSystemResult:
    """Resolve sem persistir — usado pela UI para preview live."""
    return solve_msys(msys_input)


# ==============================================================================
# F5.5 — Equilíbrio de plataforma
# ==============================================================================


def solve_equilibrium_for_input(
    msys_input: MooringSystemInput, env: EnvironmentalLoad,
) -> PlatformEquilibriumResult:
    """Resolve o equilíbrio sem persistir. Usado tanto por preview
    quanto pelo endpoint /equilibrium em sistemas salvos."""
    return solve_platform_equilibrium(msys_input, env)


def solve_equilibrium_persisted(
    db: Session, msys_id: int, env: EnvironmentalLoad,
) -> PlatformEquilibriumResult | None:
    """
    Resolve o equilíbrio para um sistema salvo. Não persiste o
    resultado em tabela (equilíbrio depende de F_env, que é input
    transiente — diferente de /solve que persiste o estado neutro).
    Devolve `None` se o sistema não existir.
    """
    rec = db.get(MooringSystemRecord, msys_id)
    if rec is None:
        return None
    msys_input = MooringSystemInput.model_validate_json(rec.config_json)
    return solve_platform_equilibrium(msys_input, env)


__all__ = [
    "EXECUTION_RETENTION",
    "create_mooring_system",
    "delete_mooring_system",
    "get_mooring_system",
    "list_mooring_systems",
    "mooring_system_record_to_output",
    "mooring_system_record_to_summary",
    "preview_solve",
    "solve_and_persist",
    "solve_equilibrium_for_input",
    "solve_equilibrium_persisted",
    "update_mooring_system",
]
