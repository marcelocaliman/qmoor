"""
Schemas Pydantic da API para Casos e Execuções.

Reusa os schemas canônicos do solver (`backend.solver.types`) em vez de
duplicá-los — qualquer evolução no solver propaga automaticamente para
a API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from backend.solver.types import (
    BoundaryConditions,
    CriteriaProfile,
    LineSegment,
    SeabedConfig,
    SolverResult,
    UtilizationLimits,
)


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope genérico de paginação (Seção 4.3 do plano F2)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)


class CaseInput(BaseModel):
    """Input canônico para criar ou atualizar um caso (Seção 4.1 do plano F2)."""

    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "example": {
                "name": "BC-01 — catenária pura suspensa",
                "description": "Wire rope 3in, lâmina 300 m, T_fl=785 kN",
                "segments": [
                    {
                        "length": 450.0,
                        "w": 201.1,
                        "EA": 3.425e7,
                        "MBL": 3.78e6,
                        "category": "Wire",
                        "line_type": "IWRCEIPS",
                    }
                ],
                "boundary": {
                    "h": 300.0,
                    "mode": "Tension",
                    "input_value": 785000.0,
                    "startpoint_depth": 0.0,
                    "endpoint_grounded": True,
                },
                "seabed": {"mu": 0.0},
                "criteria_profile": "MVP_Preliminary",
            }
        },
    )

    name: str = Field(..., min_length=1, max_length=200, description="Nome do caso")
    description: Optional[str] = Field(
        default=None, max_length=2000, description="Descrição livre (opcional)"
    )
    segments: list[LineSegment] = Field(
        ...,
        min_length=1,
        max_length=1,
        description="Lista com UM segmento (MVP v1). Multi-segmento em v2.1.",
    )
    boundary: BoundaryConditions
    seabed: SeabedConfig = Field(default_factory=SeabedConfig)
    criteria_profile: CriteriaProfile = Field(default=CriteriaProfile.MVP_PRELIMINARY)
    user_defined_limits: Optional[UtilizationLimits] = Field(
        default=None,
        description="Obrigatório quando criteria_profile = UserDefined.",
    )


class ExecutionOutput(BaseModel):
    """Representação de uma execução persistida."""

    id: int
    case_id: int
    result: SolverResult
    executed_at: datetime


class CaseSummary(BaseModel):
    """Versão enxuta do caso para listagem (sem input completo)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    line_type: Optional[str] = Field(
        default=None, description="Primeiro segmento.line_type (se informado)"
    )
    mode: str = Field(..., examples=["Tension", "Range"])
    water_depth: float = Field(..., description="Lâmina d'água em metros")
    line_length: float = Field(..., description="Comprimento da linha em metros")
    criteria_profile: str
    created_at: datetime
    updated_at: datetime


class CaseOutput(BaseModel):
    """Representação detalhada (para GET /cases/{id})."""

    id: int
    name: str
    description: Optional[str]
    input: CaseInput
    latest_executions: list[ExecutionOutput] = Field(
        default_factory=list,
        description="Últimas 10 execuções (mais recente primeiro). Vazio se nunca foi resolvido.",
    )
    created_at: datetime
    updated_at: datetime


__all__ = [
    "CaseInput",
    "CaseOutput",
    "CaseSummary",
    "ExecutionOutput",
    "PaginatedResponse",
]
