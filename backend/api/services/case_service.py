"""
Lógica de negócio para casos (CRUD).

Centraliza serialização CaseInput ↔ CaseRecord.input_json e as queries
comuns. Router fica fino.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.db.models import CaseRecord, ExecutionRecord
from backend.api.schemas.cases import (
    CaseInput,
    CaseOutput,
    CaseSummary,
    ExecutionOutput,
)
from backend.solver.types import SolverResult


# ==============================================================================
# Serialização CaseInput ↔ CaseRecord
# ==============================================================================


def _line_type_of(case_input: CaseInput) -> str | None:
    """Primeiro segmento.line_type (desnormalizado para filtros)."""
    if case_input.segments:
        return case_input.segments[0].line_type
    return None


def case_record_to_summary(rec: CaseRecord) -> CaseSummary:
    return CaseSummary(
        id=rec.id,
        name=rec.name,
        description=rec.description,
        line_type=rec.line_type,
        mode=rec.mode,
        water_depth=rec.water_depth,
        line_length=rec.line_length,
        criteria_profile=rec.criteria_profile,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def case_record_to_output(rec: CaseRecord) -> CaseOutput:
    """Hidrata CaseRecord em CaseOutput incluindo execuções."""
    case_input = CaseInput.model_validate_json(rec.input_json)
    executions = [
        ExecutionOutput(
            id=e.id,
            case_id=e.case_id,
            result=SolverResult.model_validate_json(e.result_json),
            executed_at=e.executed_at,
        )
        for e in rec.executions
    ]
    return CaseOutput(
        id=rec.id,
        name=rec.name,
        description=rec.description,
        input=case_input,
        latest_executions=executions,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


# ==============================================================================
# CRUD
# ==============================================================================


class CaseNotFound(Exception):
    """Disparado quando um case_id inexistente é consultado."""


def create_case(db: Session, case_input: CaseInput) -> CaseRecord:
    """Persiste um novo caso e retorna o registro com id/timestamps."""
    segment = case_input.segments[0]  # MVP v1: único segmento
    rec = CaseRecord(
        name=case_input.name,
        description=case_input.description,
        input_json=case_input.model_dump_json(),
        line_type=segment.line_type,
        mode=case_input.boundary.mode.value,
        water_depth=case_input.boundary.h,
        line_length=segment.length,
        criteria_profile=case_input.criteria_profile.value,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def get_case(db: Session, case_id: int) -> CaseRecord:
    """Carrega caso com execuções ou levanta CaseNotFound."""
    rec = db.get(CaseRecord, case_id)
    if rec is None:
        raise CaseNotFound(case_id)
    return rec


def update_case(
    db: Session, case_id: int, case_input: CaseInput
) -> CaseRecord:
    """Atualiza campos do caso (substitui input_json integralmente)."""
    rec = get_case(db, case_id)
    segment = case_input.segments[0]
    rec.name = case_input.name
    rec.description = case_input.description
    rec.input_json = case_input.model_dump_json()
    rec.line_type = segment.line_type
    rec.mode = case_input.boundary.mode.value
    rec.water_depth = case_input.boundary.h
    rec.line_length = segment.length
    rec.criteria_profile = case_input.criteria_profile.value
    # updated_at é atualizado automaticamente pelo SQLAlchemy via `onupdate`
    db.commit()
    db.refresh(rec)
    return rec


def delete_case(db: Session, case_id: int) -> None:
    """Remove caso (cascade deleta execuções via FK ON DELETE CASCADE)."""
    rec = get_case(db, case_id)
    db.delete(rec)
    db.commit()


def list_cases(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> tuple[Sequence[CaseRecord], int]:
    """
    Lista casos paginados. `search` filtra por `name ILIKE %search%`.
    Retorna (itens_da_pagina, total_total).
    """
    stmt = select(CaseRecord)
    count_stmt = select(func.count()).select_from(CaseRecord)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(CaseRecord.name.ilike(like))
        count_stmt = count_stmt.where(CaseRecord.name.ilike(like))
    total = db.execute(count_stmt).scalar_one()
    offset = (page - 1) * page_size
    stmt = stmt.order_by(CaseRecord.updated_at.desc()).offset(offset).limit(page_size)
    items = db.execute(stmt).scalars().all()
    return items, total


__all__ = [
    "CaseNotFound",
    "case_record_to_output",
    "case_record_to_summary",
    "create_case",
    "delete_case",
    "get_case",
    "list_cases",
    "update_case",
]
