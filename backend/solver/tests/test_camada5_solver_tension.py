"""
Testes da Camada 5 — Solver completo, modo Tension.

Cobre: fachada solve(), validações de entrada, todos os campos
obrigatórios da Seção 6 do MVP v2 no SolverResult, e BC-04 contra MoorPy.
"""
from __future__ import annotations

import math

import pytest
from moorpy.Catenary import catenary as mp_catenary

from backend.solver.solver import solve
from backend.solver.types import (
    BoundaryConditions,
    ConvergenceStatus,
    LineSegment,
    SeabedConfig,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


TOL_GEOM_REL = 5e-3
TOL_FORCE_REL = 1e-2

LBF_FT_TO_N_M = 14.593903


# Campos obrigatórios do SolverResult per Seção 6 do MVP v2 PDF
CAMPOS_OBRIGATORIOS = [
    "coords_x", "coords_y",
    "tension_x", "tension_y", "tension_magnitude",
    "fairlead_tension", "anchor_tension",
    "total_horz_distance", "endpoint_depth",
    "unstretched_length", "stretched_length", "elongation",
    "total_suspended_length", "total_grounded_length",
    "dist_to_first_td",  # pode ser None quando sem touchdown
    "angle_wrt_horz_fairlead", "angle_wrt_vert_fairlead",
    "angle_wrt_horz_anchor", "angle_wrt_vert_anchor",
    "status", "message", "H", "iterations_used",
]


def _segmento_padrao(
    length: float = 450.0, EA: float = 34.25e6, MBL: float = 3.78e6,
    w: float = 13.78 * LBF_FT_TO_N_M,
) -> LineSegment:
    return LineSegment(length=length, w=w, EA=EA, MBL=MBL)


# ==============================================================================
# Validação e campos obrigatórios
# ==============================================================================


def test_solver_retorna_todos_campos_obrigatorios() -> None:
    """
    SolverResult deve conter todos os campos listados na Seção 6 do MVP v2.
    Rodamos um caso válido (BC-01-like) e checamos presença de cada campo.
    """
    seg = _segmento_padrao()
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=785_000)
    r = solve([seg], bc)
    assert r.status == ConvergenceStatus.CONVERGED
    for campo in CAMPOS_OBRIGATORIOS:
        assert hasattr(r, campo), f"Campo obrigatório ausente: {campo}"
    assert isinstance(r.coords_x, list) and len(r.coords_x) > 0
    assert len(r.coords_x) == len(r.coords_y)
    assert len(r.tension_magnitude) == len(r.coords_x)


def test_solver_valida_lista_vazia_de_segmentos() -> None:
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=500_000)
    r = solve([], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "segmento" in r.message.lower()


def test_solver_aceita_multisegmento_e_converge() -> None:
    """F5.1: multi-segmento agora é suportado e deve convergir."""
    s1 = _segmento_padrao()
    s2 = _segmento_padrao()
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=500_000)
    r = solve([s1, s2], bc)
    assert r.status == ConvergenceStatus.CONVERGED
    assert r.fairlead_tension == pytest.approx(500_000, rel=1e-3)


def test_solver_retorna_invalid_case_para_T_insuficiente() -> None:
    """T_fl <= w·h → caso inviável (linha não sustenta peso): retorna
    INVALID_CASE com mensagem, sem propagar exceção."""
    seg = _segmento_padrao(length=100.0, w=100.0)
    bc = BoundaryConditions(h=50.0, mode=SolutionMode.TENSION, input_value=4_000.0)
    r = solve([seg], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert r.message != ""


def test_solver_utilization_calculada() -> None:
    """Campo utilization = T_fl/MBL deve ser preenchido."""
    seg = _segmento_padrao(MBL=1e6)  # 1 MN
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=500_000)
    r = solve([seg], bc)
    assert r.status == ConvergenceStatus.CONVERGED
    # utilization ~ fairlead_tension/MBL
    assert r.utilization == pytest.approx(r.fairlead_tension / 1e6, rel=1e-6)


# ==============================================================================
# BC-04 — Caso completo, modo Tension (Documento A v2.2, Seção 6.1.2)
# ==============================================================================


def test_BC04_contra_moorpy() -> None:
    """
    BC-04: Lâmina 1000 m, IWRCEIPS 3", L=1800 m, w=13.78 lbf/ft,
           MBL=850 kip, modulus=9804 kip/in², μ=0,30,
           Modo Tension, T_fl=150 t = 1471 kN.

    Com T_fl=1471 kN e T_fl_crit=426 kN, a linha está TOTALMENTE
    SUSPENSA. O atrito μ=0,30 não entra na geometria mas ainda
    deve ser tolerado (irrelevante quando L_g=0).
    """
    L = 1800.0
    h = 1000.0
    w = 13.78 * LBF_FT_TO_N_M  # ~201.1 N/m
    EA = 34.25e6  # qmoor_ea IWRCEIPS 3"
    MBL = 850e3 * 4.4482216  # 850 kip em N
    mu = 0.30
    T_fl = 150.0 * 9806.65  # 150 toneladas-força = ~1471 kN

    seg = LineSegment(length=L, w=w, EA=EA, MBL=MBL)
    bc = BoundaryConditions(h=h, mode=SolutionMode.TENSION, input_value=T_fl)
    seabed = SeabedConfig(mu=mu)

    r = solve([seg], bc, seabed=seabed)
    assert r.status == ConvergenceStatus.CONVERGED
    X_my = r.total_horz_distance

    # Validação contra MoorPy com MESMOS EA e CB
    fAH, fAV, fBH, fBV, info = mp_catenary(
        XF=X_my, ZF=h, L=L, EA=EA, W=w, CB=mu,
    )
    T_fl_mp = math.sqrt(fBH ** 2 + fBV ** 2)
    H_mp = abs(fBH)

    assert T_fl_mp == pytest.approx(T_fl, rel=TOL_FORCE_REL)
    assert H_mp == pytest.approx(r.H, rel=TOL_FORCE_REL)

    print(
        f"\nBC-04 (Tension, T_fl={T_fl/1000:.1f} kN, μ={mu}, EA={EA/1e6:.1f} MN):"
        f"\n  iters        : {r.iterations_used}"
        f"\n  status       : {r.status}"
        f"\n  X            : {X_my:.2f} m"
        f"\n  H            : my={r.H/1000:.2f} kN  MoorPy={H_mp/1000:.2f} kN"
        f"\n  T_fl         : my={r.fairlead_tension/1000:.2f} kN  MoorPy={T_fl_mp/1000:.2f} kN"
        f"\n  T_anchor     : my={r.anchor_tension/1000:.2f} kN"
        f"\n  L_stretched  : {r.stretched_length:.2f} m (Δ={r.elongation:.2f} m)"
        f"\n  L_suspended  : {r.total_suspended_length:.2f} m"
        f"\n  L_grounded   : {r.total_grounded_length:.2f} m"
        f"\n  utilization  : {r.utilization*100:.1f}%"
    )
