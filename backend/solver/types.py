"""
Estruturas de dados base do solver QMoor.

Todas as grandezas físicas em SI (m, N, Pa, N/m). Conversões só nas bordas
do sistema (UI, importação/exportação).

Referências:
  - Documento A v2.2, Seções 3.2 (variáveis), 3.5 (método numérico)
  - Documentação MVP v2, Seção 6 (saídas obrigatórias) e Seção 8 (validações)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SolutionMode(str, Enum):
    """Modo de solução — qual grandeza é input, qual é output."""

    TENSION = "Tension"  # input: T_fl; output: X_total
    RANGE = "Range"  # input: X_total; output: T_fl


class ConvergenceStatus(str, Enum):
    """Estados finais do solver (Documento A v2.2, Seção 3.5.5)."""

    CONVERGED = "converged"
    MAX_ITERATIONS = "max_iterations"
    INVALID_CASE = "invalid_case"
    NUMERICAL_ERROR = "numerical_error"
    ILL_CONDITIONED = "ill_conditioned"


class LineSegment(BaseModel):
    """
    Segmento homogêneo de linha de ancoragem.

    Grandezas em SI: comprimento em m, peso em N/m, EA e MBL em N.
    MVP v2 suporta uma única linha, portanto um único segmento.
    Multi-segmento fica para v2.1 (conforme Seção 9 do Documento A).
    """

    model_config = ConfigDict(frozen=True)

    length: float = Field(..., description="Comprimento não-esticado (m)")
    w: float = Field(..., description="Peso submerso por unidade de comprimento (N/m)")
    EA: float = Field(..., description="Rigidez axial do segmento (N)")
    MBL: float = Field(..., description="Minimum Breaking Load (N)")

    @field_validator("length", "EA", "MBL")
    @classmethod
    def _must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("deve ser > 0")
        return v

    @field_validator("w")
    @classmethod
    def _weight_nonzero(cls, v: float) -> float:
        # w > 0 para linha com peso próprio (wire, chain, poliéster não-neutralizado).
        # Se um dia tivermos linha neutra (boia distribuída), relaxar esta regra.
        if v <= 0:
            raise ValueError("peso submerso w deve ser > 0 no MVP v1")
        return v


class BoundaryConditions(BaseModel):
    """
    Condições de contorno físicas do problema.

    h é a distância vertical da âncora até o fairlead (positiva = fairlead
    acima da âncora). No modelo de fundo plano, h coincide com a lâmina
    d'água se a âncora está no seabed.
    """

    model_config = ConfigDict(frozen=True)

    h: float = Field(..., description="Distância vertical anchor→fairlead (m)")
    mode: SolutionMode
    input_value: float = Field(
        ..., description="T_fl (N) se mode=Tension; X_total (m) se mode=Range"
    )

    @field_validator("h", "input_value")
    @classmethod
    def _must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("deve ser > 0")
        return v


class SeabedConfig(BaseModel):
    """Configuração do seabed (assumido plano e horizontal no MVP v1)."""

    model_config = ConfigDict(frozen=True)

    mu: float = Field(default=0.0, ge=0.0, description="Coeficiente de atrito axial")
    depth: float = Field(
        default=0.0, ge=0.0, description="Profundidade do seabed (m). 0 = âncora no seabed."
    )


class SolverConfig(BaseModel):
    """
    Tolerâncias e limites numéricos.

    Defaults conforme Seção 3.5.3 do Documento A v2.2 (validados pelo
    engenheiro revisor, resposta P-02).
    """

    model_config = ConfigDict(frozen=True)

    horz_tolerance: float = Field(default=1e-4, gt=0, description="Erro horizontal relativo")
    vert_tolerance: float = Field(default=1e-4, gt=0, description="Erro vertical relativo")
    force_tolerance: float = Field(default=1e-3, gt=0, description="Erro relativo de força")
    elastic_tolerance: float = Field(default=1e-5, gt=0, description="Tolerância loop elástico")
    max_brent_iter: int = Field(default=100, gt=0)
    max_elastic_iter: int = Field(default=30, gt=0)
    max_bisection_iter: int = Field(default=200, gt=0)
    n_plot_points: int = Field(default=101, ge=3, description="Pontos discretos da geometria")


class SolverResult(BaseModel):
    """
    Saída completa do solver.

    Campos obrigatórios conforme Seção 6 da Documentação MVP v2:
      coords.x/y, tension.x/y, fairleadTension, totalHorzDistance,
      endpointDepth, stretchedLength/unstretchedLength, elongation,
      distToFirstTD, totalGroundedLength, suspendedLength/totalSuspendedLength,
      angleWRThorz/angleWRTvert.

    Campos adicionais (H, iterations_used, …) são diagnósticos internos.
    """

    model_config = ConfigDict(frozen=True)

    # --- Status ---
    status: ConvergenceStatus
    message: str = ""

    # --- Geometria discretizada (âncora → fairlead, em SI) ---
    coords_x: list[float] = Field(default_factory=list, description="x (m)")
    coords_y: list[float] = Field(default_factory=list, description="y (m)")

    # --- Tensão ao longo da linha ---
    tension_x: list[float] = Field(default_factory=list, description="T_horizontal (N) por nó")
    tension_y: list[float] = Field(default_factory=list, description="T_vertical (N) por nó")
    tension_magnitude: list[float] = Field(default_factory=list, description="|T| (N) por nó")

    # --- Escalares ---
    fairlead_tension: float = 0.0
    anchor_tension: float = 0.0
    total_horz_distance: float = 0.0
    endpoint_depth: float = 0.0

    # --- Comprimentos ---
    unstretched_length: float = 0.0
    stretched_length: float = 0.0
    elongation: float = 0.0
    total_suspended_length: float = 0.0
    total_grounded_length: float = 0.0
    dist_to_first_td: Optional[float] = None

    # --- Ângulos (radianos) ---
    angle_wrt_horz_fairlead: float = 0.0
    angle_wrt_vert_fairlead: float = 0.0
    angle_wrt_horz_anchor: float = 0.0
    angle_wrt_vert_anchor: float = 0.0

    # --- Diagnóstico interno ---
    H: float = 0.0  # Componente horizontal da tração (constante no trecho suspenso)
    iterations_used: int = 0
    utilization: float = 0.0  # fairlead_tension / MBL (0..1)


__all__ = [
    "BoundaryConditions",
    "ConvergenceStatus",
    "LineSegment",
    "SeabedConfig",
    "SolutionMode",
    "SolverConfig",
    "SolverResult",
]
