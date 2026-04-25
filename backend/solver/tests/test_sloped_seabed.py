"""
Testes do solver F5.3 — seabed inclinado COMPLETO (touchdown + Range).

Escopo coberto na entrega final
-------------------------------
1. Schema com slope_rad (range ±π/4).
2. Visualização da rampa no plot (frontend).
3. Solver fully-suspended em rampa (cálculo idêntico ao horizontal).
4. Solver com touchdown em rampa, modo Tension (fsolve 3D).
5. Solver com touchdown em rampa, modo Range (fsolve 2D).
6. Atrito modificado em rampa: T_anchor = T_td − μ·w·cos(θ)·L_g
   − w·sin(θ)·L_g.
7. Multi-segmento + slope: rejeitado (próxima sub-fase).

Validação
---------
F5.3 não tem benchmark contra MoorPy (que não suporta seabed inclinado).
Validamos por:
  - Limite θ → 0: bate com solver horizontal (< 0.02 % em T_anchor e X).
  - Conservação geométrica: L_g + L_s = L (rígido).
  - Tangência no touchdown: ângulo da catenária local = slope.
  - Sinal do efeito da rampa: descendente (slope < 0) aumenta T_anchor;
    ascendente (slope > 0) reduz T_anchor (gravidade na rampa + atrito).
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
# BC-SS-01 — fully-suspended em rampa = horizontal
# ==============================================================================


def test_BC_SS_01_suspended_em_rampa_5deg_bate_com_horizontal() -> None:
    """Fully-suspended (T_fl > T_crit): slope é só visual, cálculo idêntico."""
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,  # > T_crit ≈ 300 kN
    )
    r_horiz = solve([seg], bc, seabed=SeabedConfig(mu=0.0, slope_rad=0.0))
    r_tilt = solve([seg], bc, seabed=SeabedConfig(mu=0.0, slope_rad=math.radians(5)))

    assert r_horiz.status == ConvergenceStatus.CONVERGED
    assert r_tilt.status == ConvergenceStatus.CONVERGED
    assert r_tilt.fairlead_tension == pytest.approx(r_horiz.fairlead_tension, rel=1e-9)
    assert r_tilt.total_horz_distance == pytest.approx(r_horiz.total_horz_distance, rel=1e-9)


# ==============================================================================
# BC-SS-02 — touchdown em rampa descendente 5° (modo Tension)
# ==============================================================================


def test_BC_SS_02_touchdown_rampa_descendente_5deg() -> None:
    """
    Slope < 0 (anchor mais raso). Geometria força touchdown.
    Verifica: convergência, conservação L_g + L_s = L, e que a rampa
    descendente AUMENTA T_anchor vs horizontal (gravidade na rampa
    ajuda a tração no anchor).
    """
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,
    )
    r_h = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=0.0))
    r_d = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)))
    assert r_d.status == ConvergenceStatus.CONVERGED, r_d.message
    assert r_d.total_grounded_length > 0
    assert abs(r_d.total_grounded_length + r_d.total_suspended_length - seg.length) < 0.5
    # Rampa descendente: T_anchor maior que horizontal
    assert r_d.anchor_tension > r_h.anchor_tension


# ==============================================================================
# BC-SS-03 — touchdown em rampa ascendente 5°
# ==============================================================================


def test_BC_SS_03_touchdown_rampa_ascendente_5deg() -> None:
    """Slope > 0: gravidade contra anchor + atrito → T_anchor menor."""
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,
    )
    r_h = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=0.0))
    r_a = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(5)))
    assert r_a.status == ConvergenceStatus.CONVERGED, r_a.message
    assert r_a.total_grounded_length > 0
    assert abs(r_a.total_grounded_length + r_a.total_suspended_length - seg.length) < 0.5
    # Rampa ascendente: T_anchor menor que horizontal
    assert r_a.anchor_tension < r_h.anchor_tension


# ==============================================================================
# BC-SS-04 — limite θ → 0 bate com horizontal (< 0,1 %)
# ==============================================================================


def test_BC_SS_04_limite_theta_zero_bate_horizontal() -> None:
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,
    )
    r_h = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=0.0))
    r_t = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(0.001)))

    assert r_h.status == ConvergenceStatus.CONVERGED
    assert r_t.status == ConvergenceStatus.CONVERGED
    assert abs(r_t.anchor_tension - r_h.anchor_tension) / r_h.anchor_tension < 1e-3
    assert abs(r_t.total_horz_distance - r_h.total_horz_distance) / r_h.total_horz_distance < 1e-3


# ==============================================================================
# BC-SS-05 — modo Range em rampa
# ==============================================================================


def test_BC_SS_05_modo_range_em_rampa_descendente() -> None:
    """
    Modo Range em rampa também é suportado agora (fsolve 2D). Verifica
    convergência e conservação.
    """
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.RANGE, input_value=800.0,
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)))
    assert r.status == ConvergenceStatus.CONVERGED, r.message
    assert r.total_horz_distance == pytest.approx(800.0, rel=1e-3)
    assert abs(r.total_grounded_length + r.total_suspended_length - seg.length) < 0.5


def test_BC_SS_05b_modo_range_em_rampa_ascendente() -> None:
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.RANGE, input_value=820.0,
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(5)))
    assert r.status == ConvergenceStatus.CONVERGED, r.message
    assert r.total_horz_distance == pytest.approx(820.0, rel=1e-3)


# ==============================================================================
# BC-SS-06 — tangência no touchdown (ângulo de departure no anchor)
# ==============================================================================


def test_BC_SS_06_tangencia_no_touchdown() -> None:
    """
    Quando há grounded em rampa, o ângulo da linha no anchor segue a
    inclinação do seabed (linha reta sobre rampa).
    """
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,
    )
    slope = math.radians(-7)
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=slope))
    assert r.status == ConvergenceStatus.CONVERGED
    # angle_wrt_horz_anchor = slope (tangente da linha no anchor segue rampa)
    assert r.angle_wrt_horz_anchor == pytest.approx(slope, abs=1e-4)


# ==============================================================================
# BC-SS-07 — multi-segmento + slope rejeitado
# ==============================================================================


def test_BC_SS_07a_multi_segmento_em_rampa_suspended() -> None:
    """
    Multi-segmento em rampa, fully-suspended (T_fl alto): converge. Como
    a linha não toca o seabed, o slope é só visual.
    """
    s = _build_segment(length=400.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=500_000,
    )
    r = solve([s, s], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(5)))
    assert r.status == ConvergenceStatus.CONVERGED, r.message


def test_BC_SS_07a_2_multi_segmento_em_rampa_touchdown() -> None:
    """
    Multi-segmento em rampa COM touchdown: P2 da F5.3.x suportada.
    Configuração chain pendant + wire em rampa descendente.
    """
    chain = LineSegment(length=200.0, w=1500.0, EA=4.5e8, MBL=6e6, category="StuddedChain")
    wire = LineSegment(length=700.0, w=200.0, EA=4.4e8, MBL=4.8e6, category="Wire")
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=400_000,  # baixo o suficiente para touchdown
    )
    r = solve([chain, wire], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)))
    assert r.status == ConvergenceStatus.CONVERGED, r.message
    # Touchdown deve existir no chain inferior
    assert r.total_grounded_length > 0
    # Conservação: L_g + L_s ≈ L_total (rígido para o trecho na rampa)
    assert abs(
        r.total_grounded_length + r.total_suspended_length
        - (chain.length + wire.length)
    ) < 5.0  # tolerância maior por causa da elasticidade


def test_BC_SS_07b_slope_com_attachments_suportado() -> None:
    """
    F5.3.y P1: combinação de slope + attachments agora é suportada.
    O integrador grounded foi estendido para aplicar saltos em V nas
    junções entre segmentos.
    """
    chain = LineSegment(length=200.0, w=1500.0, EA=4.5e8, MBL=6e6, category="StuddedChain")
    wire = LineSegment(length=700.0, w=200.0, EA=4.4e8, MBL=4.8e6, category="Wire")
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=400_000,
    )
    boia = LineAttachment(
        kind="buoy", submerged_force=20_000.0, position_index=0, name="Boia central",
    )
    r = solve(
        [chain, wire], bc,
        seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)),
        attachments=[boia],
    )
    assert r.status == ConvergenceStatus.CONVERGED, r.message
    assert r.fairlead_tension == pytest.approx(400_000, rel=1e-3)
    # H constante (mesmo com slope, attachments e touchdown)
    Tx = r.tension_x
    # No trecho grounded, Tx = T·cos(θ) (varia com T linear).
    # No trecho suspenso, Tx = H constante. Pegamos os últimos pontos.
    Tx_susp = Tx[-30:]
    assert (max(Tx_susp) - min(Tx_susp)) / r.H < 1e-3


# ==============================================================================
# BC-SS-08 — atrito modificado em rampa
# ==============================================================================


def test_BC_SS_08_atrito_zero_em_rampa() -> None:
    """
    Sem atrito (μ=0), apenas o efeito da gravidade na rampa atua sobre
    T_anchor: T_anchor = T_td − w·sin(θ)·L_g.
    """
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,
    )
    slope = math.radians(-5)
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.0, slope_rad=slope))
    assert r.status == ConvergenceStatus.CONVERGED
    # Computa T_td esperado: w·a·sqrt(1+m²) = H·sqrt(1+m²)
    m = math.tan(slope)
    T_td_est = r.H * math.sqrt(1 + m * m)
    expected_anchor = T_td_est - 200.0 * math.sin(slope) * r.total_grounded_length
    assert r.anchor_tension == pytest.approx(expected_anchor, rel=1e-3)


# ==============================================================================
# Schema: slope_rad fora do range é rejeitado pelo Pydantic
# ==============================================================================


def test_slope_rad_fora_do_range_rejeitado() -> None:
    with pytest.raises(Exception):
        SeabedConfig(slope_rad=math.radians(60))
    with pytest.raises(Exception):
        SeabedConfig(slope_rad=math.radians(-50))


# ==============================================================================
# SOLVER_VERSION ≥ 1.4.0
# ==============================================================================


def test_solver_version_inclui_f5_3() -> None:
    seg = _build_segment(length=900.0)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=200_000,
    )
    r = solve([seg], bc, seabed=SeabedConfig(mu=0.3, slope_rad=math.radians(-5)))
    assert r.status == ConvergenceStatus.CONVERGED
    parts = r.solver_version.split(".")
    assert int(parts[0]) >= 1
    if int(parts[0]) == 1:
        assert int(parts[1]) >= 4
