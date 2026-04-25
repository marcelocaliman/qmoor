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


AttachmentKind = Literal["clump_weight", "buoy"]


class LineAttachment(BaseModel):
    """
    Elemento pontual ao longo da linha — boia (empuxo líquido) ou clump
    weight (peso adicional). F5.2 + F5.4.6a.

    A posição pode ser informada de duas formas (use **exatamente uma**):

    - `position_s_from_anchor` (m, recomendado) — arc length desde a
      âncora ao longo da linha **não-esticada**. O solver divide o
      segmento que contém essa posição em dois sub-segmentos idênticos
      durante o pré-processamento, transformando o attachment numa junção
      virtual (preserva a matemática original do solver de junções).

    - `position_index` (legacy, F5.2) — índice da junção pré-existente
      entre segmentos heterogêneos. 0 = entre seg 0 e seg 1.

    `submerged_force` é magnitude positiva (N). A direção física é
    determinada pelo `kind`:
      - `clump_weight`: tende a puxar a linha para BAIXO → V += force
      - `buoy`:         tende a empurrar a linha para CIMA  → V −= force
    """

    model_config = ConfigDict(frozen=True)

    kind: AttachmentKind
    submerged_force: float = Field(
        ..., gt=0,
        description="Força submersa líquida em N (sempre positiva)",
    )
    position_index: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "(Legacy F5.2) Índice da junção pré-existente entre "
            "segmentos. 0 = entre seg 0 e seg 1; deve ser ≤ N-2."
        ),
    )
    position_s_from_anchor: Optional[float] = Field(
        default=None,
        gt=0,
        description=(
            "Arc length desde a âncora (m), ao longo da linha "
            "não-esticada. Use este modo quando a boia/clump fica no "
            "meio de um segmento — o solver divide o segmento "
            "automaticamente. Mutuamente exclusivo com `position_index`."
        ),
    )
    name: Optional[str] = Field(
        default=None, max_length=80,
        description="Identificador legível para relatórios (ex.: 'Boia A')",
    )

    @model_validator(mode="after")
    def _exactly_one_position(self) -> "LineAttachment":
        has_idx = self.position_index is not None
        has_s = self.position_s_from_anchor is not None
        if has_idx and has_s:
            raise ValueError(
                "LineAttachment: especifique exatamente um entre "
                "`position_index` e `position_s_from_anchor` (não ambos)"
            )
        if not has_idx and not has_s:
            raise ValueError(
                "LineAttachment: é obrigatório informar `position_index` "
                "(junção entre segmentos) ou `position_s_from_anchor` "
                "(distância em m da âncora)"
            )
        return self


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
    """
    Configuração do seabed.

    Por padrão é horizontal (slope_rad = 0). F5.3 adiciona suporte a
    inclinação constante: o seabed é uma reta passando pelo anchor com
    inclinação `slope_rad` em relação à horizontal. Convenção:
      - slope_rad > 0: seabed sobe em direção ao fairlead (anchor mais
        profundo que o ponto sob o fairlead).
      - slope_rad < 0: seabed desce em direção ao fairlead.
    Range admitido: ±π/4 (≈ ±45°).
    """

    model_config = ConfigDict(frozen=True)

    mu: float = Field(default=0.0, ge=0.0, description="Coeficiente de atrito axial")
    slope_rad: float = Field(
        default=0.0,
        ge=-0.7854,  # -π/4
        le=0.7854,
        description=(
            "Inclinação do seabed em radianos (range ±π/4). "
            "Positivo = sobe na direção do fairlead. F5.3."
        ),
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

    # --- Anchor uplift (F5.4.6b) ---
    # `angle_wrt_horz_anchor` em radianos já está acima; aqui derivamos
    # uma severidade categórica. Drag anchors (mais comuns em mooring
    # offshore) toleram pouco uplift — convencional ≤ 5°. Pilars e
    # suction caissons toleram mais. Usamos 5°/15° como thresholds
    # default (drag-friendly); usuário pode sobrescrever em UI futura.
    anchor_uplift_severity: str = "ok"  # 'ok' | 'warning' | 'critical'

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

    # --- Batimetria (F5.3.z) ---
    # Profundidade do seabed nos dois pontos críticos do problema, ambos
    # medidos da superfície da água (positivo = abaixo). Em casos sem
    # slope, ambos são iguais a `water_depth`. Com slope, eles diferem
    # exatamente por `tan(slope_rad) · total_horz_distance`.
    #
    # Convenção (slope_rad > 0 = seabed sobe ao fairlead):
    #   depth_at_anchor   ≥ depth_at_fairlead  (anchor mais fundo)
    # Convenção (slope_rad < 0 = seabed desce ao fairlead):
    #   depth_at_anchor   ≤ depth_at_fairlead  (anchor mais raso)
    depth_at_anchor: float = 0.0
    depth_at_fairlead: float = 0.0


# ───────────────────────────────────────────────────────────────────────
# F5.4 — Tipos para mooring system multi-linha
# ───────────────────────────────────────────────────────────────────────


class MooringLineResult(BaseModel):
    """
    Resultado de uma linha individual dentro de um mooring system (F5.4).

    Encapsula o `SolverResult` completo da linha mais informações de
    posicionamento no plano da plataforma: posição do fairlead, posição
    da âncora e força horizontal sentida pela plataforma a partir desta
    linha. Toda geometria em metros, força em Newtons.

    Convenção: o fairlead está em
      `(R · cos(θ), R · sin(θ))`
    onde θ = azimuth em rad e R = `fairlead_radius`. A linha sai
    radialmente, então a âncora fica em
      `((R + X) · cos(θ), (R + X) · sin(θ))`
    com X = `solver_result.total_horz_distance`.

    A força horizontal sobre a plataforma vinda desta linha é a
    componente horizontal da tração no fairlead, apontando do fairlead
    em direção à âncora (ou seja, +θ — radialmente para fora):
      `horz_force_xy = H · (cos(θ), sin(θ))`
    """

    model_config = ConfigDict(frozen=True)

    line_name: str = Field(..., min_length=1, max_length=80)
    fairlead_azimuth_deg: float = Field(..., ge=0.0, lt=360.0)
    fairlead_radius: float = Field(..., gt=0.0)

    fairlead_xy: tuple[float, float] = Field(
        ..., description="Posição do fairlead no plano da plataforma (m)."
    )
    anchor_xy: tuple[float, float] = Field(
        ..., description="Posição da âncora no plano da plataforma (m)."
    )
    horz_force_xy: tuple[float, float] = Field(
        ...,
        description=(
            "Componentes Fx, Fy (N) da força horizontal exercida pela "
            "linha sobre a plataforma no plano XY do casco."
        ),
    )

    solver_result: SolverResult


class MooringSystemResult(BaseModel):
    """
    Resultado agregado de um mooring system multi-linha (F5.4).

    Cada linha é resolvida independentemente (sem equilíbrio de
    plataforma). A agregação aqui é informativa: reporta o resultante
    horizontal das forças sobre o casco e, em equilíbrio sem cargas
    externas, deve ser próximo de zero para um spread balanceado.

    `worst_alert_level` segue a hierarquia broken > red > yellow > ok;
    útil pra colorir a plan view. `n_invalid` conta linhas que não
    convergiram e portanto NÃO entram no agregado de forças.
    """

    model_config = ConfigDict(frozen=True)

    lines: list[MooringLineResult]

    aggregate_force_xy: tuple[float, float] = Field(
        ...,
        description=(
            "Soma vetorial das forças horizontais sobre a plataforma (N), "
            "ignorando linhas que não convergiram."
        ),
    )
    aggregate_force_magnitude: float = Field(..., ge=0.0)
    aggregate_force_azimuth_deg: float = Field(
        default=0.0,
        ge=0.0,
        lt=360.0,
        description=(
            "Direção do resultante. Sem significado quando "
            "`aggregate_force_magnitude` é numericamente zero."
        ),
    )

    max_utilization: float = Field(default=0.0, ge=0.0)
    worst_alert_level: AlertLevel = Field(default=AlertLevel.OK)
    n_converged: int = Field(default=0, ge=0)
    n_invalid: int = Field(default=0, ge=0)

    solver_version: str = Field(default="")


__all__ = [
    "AlertLevel",
    "AttachmentKind",
    "BoundaryConditions",
    "ConvergenceStatus",
    "CriteriaProfile",
    "LineAttachment",
    "LineCategory",
    "LineSegment",
    "MooringLineResult",
    "MooringSystemResult",
    "PROFILE_LIMITS",
    "SeabedConfig",
    "SolutionMode",
    "SolverConfig",
    "SolverResult",
    "UtilizationLimits",
    "classify_utilization",
]
