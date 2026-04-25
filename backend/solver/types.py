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
from typing import Literal, Optional

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


class AlertLevel(str, Enum):
    """
    Classificação da utilização T_fl/MBL (Seção 5 do Documento A v2.2).

    - ok:     utilização abaixo do limite amarelo (linha em regime normal)
    - yellow: atenção (padrão: T/MBL ≥ 0,50)
    - red:    limite operacional intacto atingido (padrão: T/MBL ≥ 0,60)
    - broken: linha rompida matemáticamente (T/MBL ≥ 1,00 → INVALID_CASE)
    """

    OK = "ok"
    YELLOW = "yellow"
    RED = "red"
    BROKEN = "broken"


class CriteriaProfile(str, Enum):
    """
    Perfis de critério de utilização (Seção 5 do Documento A v2.2, resposta P-04).

    - MVP_Preliminary: default simples, 0.50/0.60/1.00
    - API_RP_2SK:      intacto 0.60, danificado 0.80 (ainda 1.00 para broken)
    - DNV_placeholder: reservado para ULS/ALS/FLS; tratado como MVP até F4+
    - UserDefined:     usuário fornece yellow/red/broken ratios
    """

    MVP_PRELIMINARY = "MVP_Preliminary"
    API_RP_2SK = "API_RP_2SK"
    DNV_PLACEHOLDER = "DNV_placeholder"
    USER_DEFINED = "UserDefined"


class UtilizationLimits(BaseModel):
    """
    Limites absolutos de T_fl/MBL que disparam cada AlertLevel.

    A ordem deve ser: yellow_ratio < red_ratio < broken_ratio.
    """

    model_config = ConfigDict(frozen=True)

    yellow_ratio: float = Field(default=0.50, gt=0.0, le=1.0)
    red_ratio: float = Field(default=0.60, gt=0.0, le=1.0)
    broken_ratio: float = Field(default=1.00, gt=0.0, le=2.0)

    @model_validator(mode="after")
    def _ordered(self) -> "UtilizationLimits":
        if not (self.yellow_ratio < self.red_ratio < self.broken_ratio):
            raise ValueError(
                "limites devem satisfazer yellow < red < broken "
                f"(recebido {self.yellow_ratio}/{self.red_ratio}/{self.broken_ratio})"
            )
        return self


# Limites padrão por perfil (Seção 5 e resposta P-04 do Documento B).
PROFILE_LIMITS: dict[CriteriaProfile, UtilizationLimits] = {
    CriteriaProfile.MVP_PRELIMINARY: UtilizationLimits(
        yellow_ratio=0.50, red_ratio=0.60, broken_ratio=1.00,
    ),
    CriteriaProfile.API_RP_2SK: UtilizationLimits(
        yellow_ratio=0.50, red_ratio=0.60, broken_ratio=0.80,
    ),
    CriteriaProfile.DNV_PLACEHOLDER: UtilizationLimits(
        yellow_ratio=0.50, red_ratio=0.60, broken_ratio=1.00,
    ),
    # USER_DEFINED não tem default — o usuário obrigatoriamente passa.
}


def classify_utilization(
    utilization: float,
    profile: CriteriaProfile = CriteriaProfile.MVP_PRELIMINARY,
    user_limits: Optional[UtilizationLimits] = None,
) -> AlertLevel:
    """
    Retorna o AlertLevel dado a utilização e o perfil.

    Parâmetros
    ----------
    utilization : T_fl / MBL (adimensional, 0..∞). Valores acima de broken
                  sempre retornam BROKEN.
    profile : perfil de critério. Default MVP_PRELIMINARY.
    user_limits : obrigatório se profile == USER_DEFINED; ignorado senão.
    """
    if profile == CriteriaProfile.USER_DEFINED:
        if user_limits is None:
            raise ValueError(
                "CriteriaProfile.USER_DEFINED requer `user_limits` explicito"
            )
        limits = user_limits
    else:
        limits = PROFILE_LIMITS[profile]

    if utilization >= limits.broken_ratio:
        return AlertLevel.BROKEN
    if utilization >= limits.red_ratio:
        return AlertLevel.RED
    if utilization >= limits.yellow_ratio:
        return AlertLevel.YELLOW
    return AlertLevel.OK


LineCategory = Literal["Wire", "StuddedChain", "StudlessChain", "Polyester"]


class LineSegment(BaseModel):
    """
    Segmento homogêneo de linha de ancoragem.

    Grandezas em SI: comprimento em m, peso em N/m, EA e MBL em N.
    MVP v2 suporta uma única linha, portanto um único segmento.
    Multi-segmento fica para v2.1 (conforme Seção 9 do Documento A).

    Campos opcionais `category` e `line_type` refletem Seção 5.1 do MVP v2
    PDF e Seção 4.2 do Documento A; servem para rastreabilidade e para
    escolher defaults de atrito na Seção 4.4 quando o solo é conhecido.
    Não afetam o cálculo do solver.
    """

    model_config = ConfigDict(frozen=True)

    length: float = Field(..., description="Comprimento não-esticado (m)")
    w: float = Field(..., description="Peso submerso por unidade de comprimento (N/m)")
    EA: float = Field(..., description="Rigidez axial do segmento (N)")
    MBL: float = Field(..., description="Minimum Breaking Load (N)")
    category: Optional[LineCategory] = Field(
        default=None, description="Wire, StuddedChain, StudlessChain ou Polyester"
    )
    line_type: Optional[str] = Field(
        default=None,
        description="Identificador no catálogo (ex.: 'IWRCEIPS', 'R4Studless')",
    )
    # Metadados geométricos (não entram no cálculo do solver, mas aparecem
    # em relatórios/memoriais e na UI). Opcionais para retrocompatibilidade.
    diameter: Optional[float] = Field(
        default=None, description="Diâmetro nominal (m) — metadado"
    )
    dry_weight: Optional[float] = Field(
        default=None, description="Peso seco por unidade (N/m) — metadado"
    )
    modulus: Optional[float] = Field(
        default=None, description="Módulo axial aparente (Pa) — metadado"
    )

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

    Campos `startpoint_depth` e `endpoint_grounded` refletem Seção 5.1 do
    MVP v2 PDF. O MVP v1 assume:
      - fairlead (startpoint) na superfície → startpoint_depth = 0
      - âncora (endpoint) no seabed         → endpoint_grounded = True
    Valores diferentes são validados pelo facade solve() e geram INVALID_CASE
    com mensagem clara. Suporte para âncora elevada fica para v2+.
    """

    model_config = ConfigDict(frozen=True)

    h: float = Field(..., description="Distância vertical anchor→fairlead (m)")
    mode: SolutionMode
    input_value: float = Field(
        ..., description="T_fl (N) se mode=Tension; X_total (m) se mode=Range"
    )
    startpoint_depth: float = Field(
        default=0.0, ge=0.0,
        description="Profundidade do fairlead abaixo da superfície (m). MVP v1: sempre 0.",
    )
    endpoint_grounded: bool = Field(
        default=True,
        description="Se True, âncora está no seabed. MVP v1 exige True.",
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
    n_plot_points: int = Field(
        default=5000, ge=3,
        description=(
            "Pontos discretos da geometria (âncora → fairlead). Default 5000 "
            "entrega curva visualmente lisa em plots zoom-in; pode ser "
            "reduzido para benchmarks ou export compacto."
        ),
    )
    # Obs.: a Seção 3.5.1 do Documento A v2.2 mencionava um fallback manual
    # de bisseção (`max_bisection_iter`). Como scipy.optimize.brentq já é
    # um método híbrido Brent-Dekker com fallback de bisseção nativo e
    # nunca falhou nos 45 testes da F1b, o campo foi removido. Decisão
    # registrada em CLAUDE.md seção "Fallback de bisseção NÃO implementado".


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
    alert_level: AlertLevel = AlertLevel.OK  # classificação por CriteriaProfile

    # --- Contexto geométrico global (para plots surface-relative) ---
    # Propagados pelo facade solve() a partir de BoundaryConditions. Permitem
    # que o frontend renderize a geometria com Y=0 na superfície, fairlead
    # a y=-startpoint_depth e seabed a y=-water_depth. Opcionais para
    # compatibilidade com testes unitários que chamam diretamente o solver
    # rígido/elástico (bypassando o facade).
    water_depth: float = 0.0
    startpoint_depth: float = 0.0

    # --- Auditoria ---
    # Versão do solver que produziu este resultado. Permite identificar,
    # em uma execução antiga, qual conjunto de regras numéricas/limites foi
    # usado. Default vazio para compatibilidade com testes que constroem
    # SolverResult manualmente. O facade solve() preenche sempre.
    solver_version: str = ""

    # --- Multi-segmento (F5.1) ---
    # Índices dentro de coords_x/y onde cada segmento termina (boundary).
    # Tem N+1 entradas para N segmentos: [0, n_seg_0, n_seg_0+n_seg_1, ...].
    # Vazio para casos single-segmento (compatibilidade).
    segment_boundaries: list[int] = Field(default_factory=list)


__all__ = [
    "AlertLevel",
    "BoundaryConditions",
    "ConvergenceStatus",
    "CriteriaProfile",
    "LineCategory",
    "LineSegment",
    "PROFILE_LIMITS",
    "SeabedConfig",
    "SolutionMode",
    "SolverConfig",
    "SolverResult",
    "UtilizationLimits",
    "classify_utilization",
]
