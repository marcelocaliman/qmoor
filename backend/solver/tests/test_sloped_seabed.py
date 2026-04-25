"""
Testes do solver F5.3 — seabed inclinado (entrega: schema + visual + suspended).

Escopo da F5.3
--------------
Esta sub-fase entrega:
  1. SeabedConfig.slope_rad como campo (default 0, range ±π/4).
  2. Visualização da rampa no plot (frontend).
  3. Solver para fully-suspended em rampa (cálculo idêntico ao horizontal,
     já que a linha não toca o seabed; slope é metadado visual).

Touchdown em rampa NÃO está nesta entrega — exige sistema de equações
com tangência no touchdown e atrito modificado, e a implementação não
convergiu de forma robusta. Fica como roadmap.

Casos cobertos
--------------
BC-SS-01: fully-suspended em rampa 5° = solver horizontal idêntico.
BC-SS-02: rampa 10° + fully-suspended ainda funciona.
BC-SS-03: touchdown em rampa rejeitado com mensagem orientadora.
BC-SS-04: slope com multi-segmento → INVALID_CASE.
BC-SS-05: slope com modo Range → INVALID_CASE.
BC-SS-06: SOLVER_VERSION reflete F5.3.
"""
from __future__ import annotations

import math

import pytest

from backend.solver.solver import solve
from backend.solver.types import (
    BoundaryConditions,
    ConvergenceStatus,
    LineAttachment,
    LineSegment,
    SeabedConfig,
    SolutionMode,
)


def _build_segment(length: float = 600.0) -> LineSegment:
    return LineSegment(length=length, w=200.0, EA=4.4e8, MBL=4.8e6, category="Wire")


# ==============================================================================
# BC-SS-01 — fully-suspended em rampa 5° bate com horizontal
# ==============================================================================


def test_BC_SS_01_suspended_em_rampa_5deg_bate_com_horizontal() -> None:
    """
    Fully-suspended (T_fl > T_crit) com slope ≠ 0 deve produzir geometria
    idêntica ao caso horizontal — a linha não toca o seabed, então o slope
    é apenas referência visual.
    """
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,  # > T_crit ≈ 300 kN
    )
    r_horiz = solve([seg], bc, seabed=SeabedConfig(mu=0.0, slope_rad=0.0))
    r_tilt = solve([seg], bc, seabed=SeabedConfig(mu=0.0, slope_rad=math.radians(5)))

    assert r_horiz.status == ConvergenceStatus.CONVERGED
    assert r_tilt.status == ConvergenceStatus.CONVERGED
    # Slope sem touchdown não muda nada na geometria
    assert r_tilt.fairlead_tension == pytest.approx(r_horiz.fairlead_tension, rel=1e-9)
    assert r_tilt.total_horz_distance == pytest.approx(r_horiz.total_horz_distance, rel=1e-9)
    assert r_tilt.H == pytest.approx(r_horiz.H, rel=1e-9)


# ==============================================================================
# BC-SS-02 — rampa 10° fully-suspended
# ==============================================================================


def test_BC_SS_02_rampa_10deg_suspended() -> None:
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-10)))
    assert r.status == ConvergenceStatus.CONVERGED


# ==============================================================================
# BC-SS-03 — touchdown em rampa rejeitado com mensagem clara
# ==============================================================================


def test_BC_SS_03_touchdown_em_rampa_rejeitado() -> None:
    """
    Para T_fl < T_crit, o caso seria touchdown — não suportado em rampa
    nesta sub-fase. Solver retorna INVALID_CASE com mensagem orientadora.
    """
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,  # < T_crit
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)))
    assert r.status == ConvergenceStatus.INVALID_CASE
    msg = r.message.lower()
    assert "touchdown" in msg or "rampa" in msg or "incl" in msg


# ==============================================================================
# BC-SS-04 — slope com multi-segmento ou attachments → INVALID
# ==============================================================================


def test_BC_SS_04a_slope_com_multi_segmento_invalida() -> None:
    s = _build_segment(length=400.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,
    )
    r = solve([s, s], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(5)))
    assert r.status == ConvergenceStatus.INVALID_CASE


def test_BC_SS_04b_slope_com_attachments_invalida() -> None:
    s = _build_segment(length=400.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,
    )
    boia = LineAttachment(kind="buoy", submerged_force=10_000.0, position_index=0)
    r = solve(
        [s, s], bc,
        seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(5)),
        attachments=[boia],
    )
    assert r.status == ConvergenceStatus.INVALID_CASE


# ==============================================================================
# BC-SS-05 — modo Range em rampa
# ==============================================================================


def test_BC_SS_05_modo_range_em_rampa_invalida() -> None:
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.RANGE, input_value=600.0,
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(5)))
    assert r.status == ConvergenceStatus.INVALID_CASE


# ==============================================================================
# BC-SS-06 — SOLVER_VERSION sobe com F5.3
# ==============================================================================


def test_solver_version_inclui_f5_3() -> None:
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)))
    assert r.status == ConvergenceStatus.CONVERGED
    parts = r.solver_version.split(".")
    assert int(parts[0]) >= 1
    if int(parts[0]) == 1:
        assert int(parts[1]) >= 4, f"F5.3 requer SOLVER_VERSION ≥ 1.4.x, got {r.solver_version}"


# ==============================================================================
# Schema: slope_rad fora do range é rejeitado pelo Pydantic
# ==============================================================================


def test_slope_rad_fora_do_range_rejeitado() -> None:
    """slope_rad > π/4 ou < -π/4 cai na validação Pydantic."""
    with pytest.raises(Exception):  # ValidationError
        SeabedConfig(slope_rad=math.radians(60))
    with pytest.raises(Exception):
        SeabedConfig(slope_rad=math.radians(-50))
