"""
Endpoints REST de mooring systems (F5.4.2).

Rotas (montadas em /api/v1):
  GET    /mooring-systems
  POST   /mooring-systems
  GET    /mooring-systems/{id}
  PUT    /mooring-systems/{id}
  DELETE /mooring-systems/{id}
  POST   /mooring-systems/{id}/solve
  POST   /mooring-systems/preview-solve
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.api.db.session import get_db
from backend.api.schemas.cases import PaginatedResponse
from backend.api.schemas.errors import ErrorResponse
from backend.api.schemas.mooring_systems import (
    MooringSystemExecutionOutput,
    MooringSystemInput,
    MooringSystemOutput,
    MooringSystemSummary,
)
from backend.api.services import mooring_system_service
from backend.api.services.pdf_report import build_mooring_system_pdf
from backend.solver.types import (
    EnvironmentalLoad,
    MooringSystemResult,
    PlatformEquilibriumResult,
)
from pydantic import BaseModel, Field


class EquilibriumRequest(BaseModel):
    """Body do POST /equilibrium — carga ambiental sobre a plataforma."""

    Fx: float = Field(default=0.0, description="Componente X (N)")
    Fy: float = Field(default=0.0, description="Componente Y (N)")
    Mz: float = Field(default=0.0, description="Momento Z (N·m, reservado)")

router = APIRouter(prefix="/mooring-systems", tags=["mooring-systems"])


def _msys_not_found(msys_id: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "mooring_system_not_found",
            "message": f"Mooring system id={msys_id} não encontrado.",
        },
    )


@router.get(
    "",
    response_model=PaginatedResponse[MooringSystemSummary],
    summary="Listar mooring systems",
    description=(
        "Lista sistemas multi-linha salvos, paginados e ordenados por "
        "updated_at desc. Use `search` para filtrar por nome."
    ),
)
def list_mooring_systems(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MooringSystemSummary]:
    items, total = mooring_system_service.list_mooring_systems(
        db, page=page, page_size=page_size, search=search,
    )
    return PaginatedResponse[MooringSystemSummary](
        items=[
            mooring_system_service.mooring_system_record_to_summary(i)
            for i in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=MooringSystemOutput,
    status_code=status.HTTP_201_CREATED,
    summary="Criar mooring system",
    responses={422: {"model": ErrorResponse}},
)
def create_mooring_system(
    msys_input: MooringSystemInput, db: Session = Depends(get_db)
) -> MooringSystemOutput:
    rec = mooring_system_service.create_mooring_system(db, msys_input)
    return mooring_system_service.mooring_system_record_to_output(rec)


@router.post(
    "/preview-solve",
    response_model=MooringSystemResult,
    summary="Preview live (sem persistir)",
    description=(
        "Resolve um mooring system para preview da UI sem persistir no "
        "banco. Linhas que falham aparecem no resultado com status "
        "diferente de `converged`; agregado ignora as não-convergidas."
    ),
)
def preview_solve(msys_input: MooringSystemInput) -> MooringSystemResult:
    return mooring_system_service.preview_solve(msys_input)


@router.get(
    "/{msys_id}",
    response_model=MooringSystemOutput,
    summary="Detalhar mooring system",
    description=(
        "Retorna a configuração completa do sistema e até as últimas "
        "10 execuções do solver multi-linha (mais recentes primeiro)."
    ),
    responses={404: {"model": ErrorResponse}},
)
def get_mooring_system(
    msys_id: int, db: Session = Depends(get_db)
) -> MooringSystemOutput:
    rec = mooring_system_service.get_mooring_system(db, msys_id)
    if rec is None:
        raise _msys_not_found(msys_id)
    return mooring_system_service.mooring_system_record_to_output(rec)


@router.put(
    "/{msys_id}",
    response_model=MooringSystemOutput,
    summary="Atualizar mooring system",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def update_mooring_system(
    msys_id: int,
    msys_input: MooringSystemInput,
    db: Session = Depends(get_db),
) -> MooringSystemOutput:
    rec = mooring_system_service.update_mooring_system(db, msys_id, msys_input)
    if rec is None:
        raise _msys_not_found(msys_id)
    return mooring_system_service.mooring_system_record_to_output(rec)


@router.delete(
    "/{msys_id}",
    status_code=status.HTTP_200_OK,
    summary="Remover mooring system",
    description=(
        "Remove o sistema e todas as execuções (cascade ON DELETE)."
    ),
    responses={404: {"model": ErrorResponse}},
)
def delete_mooring_system(
    msys_id: int, db: Session = Depends(get_db)
) -> dict[str, str]:
    ok = mooring_system_service.delete_mooring_system(db, msys_id)
    if not ok:
        raise _msys_not_found(msys_id)
    return {"status": "deleted", "message": f"Mooring system id={msys_id} removido."}


@router.post(
    "/{msys_id}/solve",
    response_model=MooringSystemExecutionOutput,
    summary="Resolver mooring system",
    description=(
        "Resolve cada linha do sistema (sem equilíbrio de plataforma) e "
        "agrega as forças horizontais no plano da plataforma. "
        "Persiste a execução; retenção das 10 mais recentes por sistema. "
        "Linhas que não convergem ficam de fora do agregado mas o "
        "resultado parcial é persistido (UI mostra `n_invalid`)."
    ),
    responses={404: {"model": ErrorResponse}},
)
def solve_mooring_system(
    msys_id: int, db: Session = Depends(get_db)
) -> MooringSystemExecutionOutput:
    out = mooring_system_service.solve_and_persist(db, msys_id)
    if out is None:
        raise _msys_not_found(msys_id)
    _, exec_rec = out
    from backend.solver.types import MooringSystemResult as _Result
    return MooringSystemExecutionOutput(
        id=exec_rec.id,
        mooring_system_id=exec_rec.mooring_system_id,
        result=_Result.model_validate_json(exec_rec.result_json),
        executed_at=exec_rec.executed_at,
    )


@router.get(
    "/{msys_id}/export/json",
    response_model=MooringSystemOutput,
    summary="Exportar mooring system como JSON normalizado",
    description=(
        "Retorna o `MooringSystemOutput` completo (input + últimas execuções). "
        "Equivalente ao GET, com header `Content-Disposition: attachment` para "
        "download direto pelo browser."
    ),
    responses={404: {"model": ErrorResponse}},
)
def export_mooring_system_json(
    msys_id: int, db: Session = Depends(get_db)
):
    rec = mooring_system_service.get_mooring_system(db, msys_id)
    if rec is None:
        raise _msys_not_found(msys_id)
    out = mooring_system_service.mooring_system_record_to_output(rec)
    from fastapi.responses import JSONResponse

    # Filename precisa ser ASCII puro: o header Content-Disposition é
    # Latin-1 por padrão e não aceita caracteres acentuados / símbolos
    # (×, é, etc.) que aparecem em nomes de sistemas em pt-BR.
    safe_name = "".join(
        c if (c.isascii() and (c.isalnum() or c in ("-", "_"))) else "_"
        for c in rec.name
    )[:50] or f"mooring_system_{msys_id}"
    filename = f"qmoor_msys_{safe_name}.json"
    return JSONResponse(
        content=out.model_dump(mode="json"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/{msys_id}/export/pdf",
    summary="Exportar relatório técnico em PDF",
    description=(
        "Gera um PDF A4 com header, disclaimer técnico, tabela de "
        "configuração, plan view (matplotlib), tabela de agregados e "
        "tabela detalhada por linha. Usa a **última execução** do "
        "sistema; se nunca foi resolvido, gera relatório parcial só "
        "com as entradas e plan view com âncoras estimadas."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF gerado com sucesso",
        },
        404: {"model": ErrorResponse},
    },
)
def export_mooring_system_pdf(
    msys_id: int, db: Session = Depends(get_db)
) -> Response:
    rec = mooring_system_service.get_mooring_system(db, msys_id)
    if rec is None:
        raise _msys_not_found(msys_id)
    latest = rec.executions[0] if rec.executions else None
    pdf_bytes = build_mooring_system_pdf(rec, latest)
    safe_name = "".join(
        c if (c.isascii() and (c.isalnum() or c in ("-", "_"))) else "_"
        for c in rec.name
    )[:50] or f"mooring_system_{msys_id}"
    filename = f"qmoor_msys_{safe_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post(
    "/{msys_id}/equilibrium",
    response_model=PlatformEquilibriumResult,
    summary="Equilíbrio de plataforma sob carga ambiental (F5.5)",
    description=(
        "Dada uma carga horizontal F_env sobre a plataforma, encontra "
        "o offset (Δx, Δy) tal que a soma das forças horizontais das "
        "linhas restauradoras + F_env = 0. Cada linha é resolvida no "
        "novo arranjo geométrico (fairlead deslocado) em modo Range.\n\n"
        "**Não persiste**: equilíbrio depende de F_env, que é input "
        "transiente. A UI tipicamente roda este endpoint à medida que "
        "o usuário ajusta os sliders de carga."
    ),
    responses={404: {"model": ErrorResponse}},
)
def equilibrium(
    msys_id: int,
    body: EquilibriumRequest,
    db: Session = Depends(get_db),
) -> PlatformEquilibriumResult:
    env = EnvironmentalLoad(Fx=body.Fx, Fy=body.Fy, Mz=body.Mz)
    res = mooring_system_service.solve_equilibrium_persisted(db, msys_id, env)
    if res is None:
        raise _msys_not_found(msys_id)
    return res


@router.post(
    "/equilibrium-preview",
    response_model=PlatformEquilibriumResult,
    summary="Preview de equilíbrio (sem persistir, sem id)",
    description=(
        "Resolve equilíbrio recebendo o input completo + carga "
        "ambiental no body. Útil para preview live durante a edição "
        "(quando o sistema ainda não foi salvo)."
    ),
)
def equilibrium_preview(
    body: dict,
) -> PlatformEquilibriumResult:
    """Body é {"system": MooringSystemInput, "env": {Fx, Fy, Mz?}}."""
    msys_input = MooringSystemInput.model_validate(body.get("system", {}))
    env_dict = body.get("env", {}) or {}
    env = EnvironmentalLoad(
        Fx=float(env_dict.get("Fx", 0.0)),
        Fy=float(env_dict.get("Fy", 0.0)),
        Mz=float(env_dict.get("Mz", 0.0)),
    )
    return mooring_system_service.solve_equilibrium_for_input(msys_input, env)


__all__ = ["router"]
