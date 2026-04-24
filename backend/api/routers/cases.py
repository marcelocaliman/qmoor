"""
Endpoints CRUD de casos (Seção 3.1 do docs/plano_F2_api.md).

Rotas:
  GET    /api/v1/cases
  POST   /api/v1/cases
  GET    /api/v1/cases/{id}
  PUT    /api/v1/cases/{id}
  DELETE /api/v1/cases/{id}

O endpoint /api/v1/cases/{id}/solve mora em routers/solve.py (F2.4).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.db.session import get_db
from backend.api.schemas.cases import (
    CaseInput,
    CaseOutput,
    CaseSummary,
    PaginatedResponse,
)
from backend.api.schemas.errors import ErrorResponse
from backend.api.services import case_service

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_not_found(case_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "case_not_found",
            "message": f"Caso id={case_id} não encontrado.",
        },
    )


@router.get(
    "",
    response_model=PaginatedResponse[CaseSummary],
    summary="Listar casos",
    description=(
        "Lista casos salvos, paginados e ordenados por updated_at "
        "desc. Use `search` para filtrar por nome."
    ),
)
def list_cases(
    page: int = Query(default=1, ge=1, description="Página (1-indexed)."),
    page_size: int = Query(
        default=20, ge=1, le=100, description="Itens por página (máx. 100)."
    ),
    search: Optional[str] = Query(
        default=None, description="Filtro ILIKE sobre o nome do caso."
    ),
    db: Session = Depends(get_db),
) -> PaginatedResponse[CaseSummary]:
    items, total = case_service.list_cases(
        db, page=page, page_size=page_size, search=search,
    )
    return PaginatedResponse[CaseSummary](
        items=[case_service.case_record_to_summary(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=CaseOutput,
    status_code=status.HTTP_201_CREATED,
    summary="Criar caso",
    description="Valida e persiste um novo caso. Retorna o caso com id e timestamps.",
    responses={
        422: {
            "model": ErrorResponse,
            "description": "Entrada inválida (Pydantic validation).",
        },
    },
)
def create_case(
    case_input: CaseInput, db: Session = Depends(get_db)
) -> CaseOutput:
    rec = case_service.create_case(db, case_input)
    return case_service.case_record_to_output(rec)


@router.get(
    "/{case_id}",
    response_model=CaseOutput,
    summary="Detalhar caso",
    description=(
        "Retorna o input completo do caso e até as últimas 10 execuções "
        "(mais recentes primeiro)."
    ),
    responses={404: {"model": ErrorResponse}},
)
def get_case(case_id: int, db: Session = Depends(get_db)) -> CaseOutput:
    try:
        rec = case_service.get_case(db, case_id)
    except case_service.CaseNotFound:
        raise _case_not_found(case_id)
    return case_service.case_record_to_output(rec)


@router.put(
    "/{case_id}",
    response_model=CaseOutput,
    summary="Atualizar caso",
    description="Substitui o input do caso. Execuções anteriores são preservadas.",
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def update_case(
    case_id: int, case_input: CaseInput, db: Session = Depends(get_db)
) -> CaseOutput:
    try:
        rec = case_service.update_case(db, case_id, case_input)
    except case_service.CaseNotFound:
        raise _case_not_found(case_id)
    return case_service.case_record_to_output(rec)


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_200_OK,
    summary="Remover caso",
    description=(
        "Remove o caso e todas as suas execuções (cascade via ON DELETE "
        "CASCADE). Retorna corpo vazio."
    ),
    responses={404: {"model": ErrorResponse}},
)
def delete_case(case_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        case_service.delete_case(db, case_id)
    except case_service.CaseNotFound:
        raise _case_not_found(case_id)
    return {"status": "deleted", "message": f"Caso id={case_id} removido."}


__all__ = ["router"]
