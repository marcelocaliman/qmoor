"""
Testes da Camada 2 — Touchdown no seabed sem atrito (μ=0).

Cobre: find_touchdown, valores críticos de transição suspenso↔touchdown,
e benchmark BC-09 contra MoorPy (μ=0, touchdown, sem elasticidade).
"""
from __future__ import annotations

import math

import pytest
from moorpy.Catenary import catenary as mp_catenary

from backend.solver.catenary import solve_rigid_suspended
from backend.solver.seabed import (
    critical_range_for_touchdown,
    critical_tension_for_touchdown,
    find_touchdown,
    solve_with_seabed_no_friction,
)
from backend.solver.types import (
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
)


TOL_GEOM_REL = 5e-3  # 0,5%
TOL_FORCE_REL = 1e-2  # 1,0%
TOL_GROUNDED_REL = 2e-2  # 2,0% em grounded length (Seção 6.3 Documento A)

LBF_FT_TO_N_M = 14.593903


# ==============================================================================
# Helpers
# ==============================================================================


def test_find_touchdown_identidades_hiperbolicas() -> None:
    """Para h=0: X_s = 0, L_s = 0."""
    X_s, L_s = find_touchdown(a=100.0, w=1.0, h=0.0)
    assert X_s == pytest.approx(0.0)
    assert L_s == pytest.approx(0.0)


def test_find_touchdown_consistencia_com_helpers_camada1() -> None:
    """
    find_touchdown retorna (X_s, L_s) tais que
    catenary_length(a, X_s) == L_s e catenary_height(a, X_s) == h.
    """
    a = 200.0
    h = 300.0
    X_s, L_s = find_touchdown(a=a, w=1.0, h=h)
    # Verifica h: a·(cosh(X_s/a)−1) == h
    h_rec = a * (math.cosh(X_s / a) - 1.0)
    assert h_rec == pytest.approx(h, rel=1e-9)
    # Verifica L_s: a·sinh(X_s/a) == L_s
    L_rec = a * math.sinh(X_s / a)
    assert L_rec == pytest.approx(L_s, rel=1e-9)


def test_critical_tension_fronteira() -> None:
    """
    Na fronteira T_fl = T_fl_crit: solver suspenso dá s_a ≈ 0 (ancora no
    vértice), e touchdown-dispatch dá L_g ≈ 0. Ambos devem convergir a
    geometrias próximas.
    """
    L, h, w = 500.0, 300.0, 200.0
    T_crit = critical_tension_for_touchdown(L, h, w)
    r_sup = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_crit * 1.001,
    )
    r_inf = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_crit * 0.999,
    )
    # Ambos devem convergir
    assert r_sup.status == ConvergenceStatus.CONVERGED
    assert r_inf.status == ConvergenceStatus.CONVERGED
    # Trecho suspenso em r_sup ≈ L; em r_inf ≈ L (quase nenhum grounded ainda)
    assert r_sup.total_grounded_length == pytest.approx(0.0, abs=1.0)
    assert r_inf.total_grounded_length < 5.0
    # Geometria (X e T_fl) próximos
    assert r_sup.total_horz_distance == pytest.approx(
        r_inf.total_horz_distance, rel=1e-2
    )


def test_critical_range_fronteira() -> None:
    """Mesma ideia para Mode Range: na fronteira, dispatch é consistente."""
    L, h = 500.0, 300.0
    X_crit = critical_range_for_touchdown(L, h)
    r_sup = solve_rigid_suspended(
        L=L, h=h, w=200.0, mode=SolutionMode.RANGE, input_value=X_crit * 0.999,
    )
    r_inf = solve_rigid_suspended(
        L=L, h=h, w=200.0, mode=SolutionMode.RANGE, input_value=X_crit * 1.001,
    )
    assert r_sup.status == ConvergenceStatus.CONVERGED
    assert r_inf.status == ConvergenceStatus.CONVERGED


# ==============================================================================
# Touchdown básico
# ==============================================================================


def test_touchdown_basico_tension_mode() -> None:
    """
    Caso óbvio: linha longa, tração moderada → touchdown com grande L_g.
    Verifica consistência interna: L_s + L_g = L, X_s + L_g = X_total.
    """
    L = 1000.0
    h = 100.0
    w = 100.0
    T_fl = 15000.0  # < T_fl_crit

    r = solve_with_seabed_no_friction(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl,
    )
    assert r.status == ConvergenceStatus.CONVERGED
    assert r.total_grounded_length > 0
    assert r.total_grounded_length + r.total_suspended_length == pytest.approx(L, rel=1e-6)
    # Tension mode: T_fl de saída deve bater com input
    assert r.fairlead_tension == pytest.approx(T_fl, rel=1e-6)
    # Sem atrito (μ=0): T_anchor = H = T_touchdown
    assert r.anchor_tension == pytest.approx(r.H, rel=1e-9)


def test_touchdown_basico_range_mode() -> None:
    """
    Mode Range com touchdown: consistência interna.
    Escolhemos X tal que L − X < h (regime de touchdown clássico; se
    L − X > h, cai em caso patológico com trecho slack — tratado em Camada 7).
    """
    L = 500.0
    h = 100.0
    w = 100.0
    X_total = 450.0  # L − X = 50 < h = 100 (OK)

    r = solve_with_seabed_no_friction(
        L=L, h=h, w=w, mode=SolutionMode.RANGE, input_value=X_total,
    )
    assert r.status == ConvergenceStatus.CONVERGED
    assert r.total_horz_distance == pytest.approx(X_total, rel=1e-6)
    assert r.total_grounded_length + r.total_suspended_length == pytest.approx(L, rel=1e-6)
    assert r.total_grounded_length > 0


def test_consistencia_tension_range_touchdown() -> None:
    """
    Para touchdown: resolve Tension, pega X, resolve Range com esse X,
    deve recuperar T_fl original.
    """
    L, h, w = 1000.0, 100.0, 100.0
    T_fl_in = 15000.0
    r_t = solve_with_seabed_no_friction(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl_in,
    )
    X = r_t.total_horz_distance
    r_r = solve_with_seabed_no_friction(
        L=L, h=h, w=w, mode=SolutionMode.RANGE, input_value=X,
    )
    assert r_r.fairlead_tension == pytest.approx(T_fl_in, rel=1e-6)
    assert r_r.total_grounded_length == pytest.approx(r_t.total_grounded_length, rel=1e-6)


# ==============================================================================
# BC-09 — μ=0, touchdown (derivado de BC-04 mas com atrito zero)
# ==============================================================================


def test_BC09_contra_moorpy() -> None:
    """
    BC-09 — μ=0, touchdown.

    O Documento A v2.2, Seção 6.2, deixa BC-09 com "entradas a definir"
    (sugere gerar variações dos casos base). O revisor indicou somente
    a premissa μ=0 + touchdown; com os parâmetros geométricos de BC-04
    (h=1000, L=1800, T_fl=1471 kN) a linha estaria totalmente suspensa
    (T_fl_crit = 426 kN < 1471 kN).

    Escolhemos aqui parâmetros que garantem touchdown claro e grande
    trecho apoiado, mantendo o tipo de linha (IWRCEIPS 3"):
      h=300 m, L=700 m, w=13.78 lbf/ft (~201 N/m)
      Modo Tension, T_fl=150 kN  (< T_fl_crit ≈ 194 kN).

    Validação contra MoorPy (CB=0 para μ=0 → sem atrito seabed).
    """
    L = 700.0
    h = 300.0
    w = 13.78 * LBF_FT_TO_N_M  # ~201.1 N/m
    T_fl_input = 150_000.0  # 150 kN
    EA_rigid = 1e15

    # Sanity: esperamos touchdown
    T_fl_crit = critical_tension_for_touchdown(L, h, w)
    assert T_fl_input < T_fl_crit, (
        f"BC-09 configurado errado: T_fl_input ({T_fl_input:.0f}) >= T_fl_crit "
        f"({T_fl_crit:.0f}); caso não teria touchdown"
    )

    # Minha solução (deve dispatar para touchdown via solve_rigid_suspended)
    my = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl_input,
    )
    assert my.status == ConvergenceStatus.CONVERGED
    assert my.total_grounded_length > 0, "BC-09 deveria ter L_g > 0"
    X_my = my.total_horz_distance
    H_my = my.H
    L_g_my = my.total_grounded_length

    # MoorPy no X obtido
    fAH, fAV, fBH, fBV, info = mp_catenary(
        XF=X_my, ZF=h, L=L, EA=EA_rigid, W=w, CB=0,
    )
    T_fl_mp = math.sqrt(fBH ** 2 + fBV ** 2)
    H_mp = abs(fBH)
    LBot_mp = info.get("LBot", 0.0)

    # Comparações
    assert T_fl_mp == pytest.approx(T_fl_input, rel=TOL_FORCE_REL), (
        f"T_fl: my input={T_fl_input:.1f}, MoorPy={T_fl_mp:.1f}"
    )
    assert H_mp == pytest.approx(H_my, rel=TOL_FORCE_REL)
    assert LBot_mp == pytest.approx(L_g_my, rel=TOL_GROUNDED_REL), (
        f"Grounded: my={L_g_my:.3f} m, MoorPy={LBot_mp:.3f} m"
    )

    print(
        f"\nBC-09 comparativo:"
        f"\n  T_fl input : {T_fl_input/1000:.2f} kN   crit: {T_fl_crit/1000:.2f} kN"
        f"\n  X          : my={X_my:.2f} m"
        f"\n  H          : my={H_my/1000:.2f} kN   MoorPy={H_mp/1000:.2f} kN"
        f"\n  T_fl       : my={my.fairlead_tension/1000:.2f} kN   MoorPy={T_fl_mp/1000:.2f} kN"
        f"\n  L_grounded : my={L_g_my:.2f} m   MoorPy={LBot_mp:.2f} m"
    )
