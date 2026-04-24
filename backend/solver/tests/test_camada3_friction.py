"""
Testes da Camada 3 — Atrito de Coulomb no trecho apoiado (μ > 0).

Cobre: apply_seabed_friction (perfil linear e caso slack), equivalência
com Camada 2 quando μ=0, caso μ alto (tração anulada), e benchmarks
BC-02 (μ moderado) e BC-08 (μ=1,0) contra MoorPy.
"""
from __future__ import annotations

import math

import pytest
from moorpy.Catenary import catenary as mp_catenary

from backend.solver.catenary import solve_rigid_suspended
from backend.solver.friction import (
    apply_seabed_friction,
    solve_with_seabed_friction,
)
from backend.solver.seabed import solve_with_seabed_no_friction
from backend.solver.types import (
    ConvergenceStatus,
    SolutionMode,
)


TOL_GEOM_REL = 5e-3
TOL_FORCE_REL = 1e-2
TOL_GROUNDED_REL = 2e-2

LBF_FT_TO_N_M = 14.593903


# ==============================================================================
# apply_seabed_friction — helper
# ==============================================================================


def test_apply_seabed_friction_sem_atrito() -> None:
    """μ=0: T(s) = T_touchdown constante em todo o grounded."""
    prof = apply_seabed_friction(T_touchdown=10_000, w=100, mu=0.0, L_g=50, n=11)
    assert prof.T_anchor == pytest.approx(10_000)
    assert prof.s_slack == 0.0
    assert all(abs(t - 10_000) < 1e-9 for t in prof.T)


def test_apply_seabed_friction_perfil_linear() -> None:
    """
    μ moderado sem slack: T cresce linearmente de T_anchor (na âncora)
    a T_touchdown (no touchdown).
    """
    T_td = 10_000
    w = 100
    mu = 0.3
    L_g = 50
    prof = apply_seabed_friction(T_touchdown=T_td, w=w, mu=mu, L_g=L_g, n=11)

    # T_anchor pela fórmula: max(0, T_td − μ·w·L_g) = 10000 − 0.3·100·50 = 10000 − 1500 = 8500
    assert prof.T_anchor == pytest.approx(T_td - mu * w * L_g)
    assert prof.s_slack == 0.0
    # T[0] = T_anchor (na âncora), T[-1] = T_td (no touchdown)
    assert prof.T[0] == pytest.approx(prof.T_anchor)
    assert prof.T[-1] == pytest.approx(T_td)


def test_apply_seabed_friction_caso_slack() -> None:
    """
    μ·w·L_g > T_touchdown: parte do trecho fica com T=0 (slack). s_slack
    marca a fronteira; além dele, T cresce linearmente até T_touchdown.
    """
    T_td = 1_000
    w = 100
    mu = 1.0
    L_g = 50  # μ·w·L_g = 5000 > 1000 → slack até s_slack = 50 − 10 = 40
    prof = apply_seabed_friction(T_touchdown=T_td, w=w, mu=mu, L_g=L_g, n=51)

    assert prof.T_anchor == 0.0
    assert prof.s_slack == pytest.approx(40.0)
    # Antes do s_slack: T = 0. Depois: T crescente até T_td.
    for si, ti in zip(prof.s, prof.T):
        if si < prof.s_slack - 1e-9:
            assert ti == 0.0
        else:
            # Linear: T(s) = μ·w·(s − s_slack)
            assert ti == pytest.approx(mu * w * (si - prof.s_slack), abs=1e-6)


# ==============================================================================
# Equivalência Camada 3 (μ=0) ≡ Camada 2
# ==============================================================================


def test_atrito_zero_equivale_camada2() -> None:
    """solve_with_seabed_friction(μ=0) deve dar exatamente o mesmo resultado
    que solve_with_seabed_no_friction para o mesmo caso."""
    L, h, w = 700.0, 300.0, 13.78 * LBF_FT_TO_N_M
    T_fl = 150_000.0
    r2 = solve_with_seabed_no_friction(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl,
    )
    r3 = solve_with_seabed_friction(
        L=L, h=h, w=w, mu=0.0, mode=SolutionMode.TENSION, input_value=T_fl,
    )
    assert r3.total_horz_distance == pytest.approx(r2.total_horz_distance, rel=1e-12)
    assert r3.total_grounded_length == pytest.approx(r2.total_grounded_length, rel=1e-12)
    assert r3.anchor_tension == pytest.approx(r2.anchor_tension, rel=1e-9)
    assert r3.H == pytest.approx(r2.H, rel=1e-12)


def test_atrito_alto_anula_tracao() -> None:
    """
    Com μ alto e L_g grande, T_anchor → 0 (linha frouxa junto à âncora).
    A geometria (X, H, fairlead_tension) NÃO depende de μ — apenas T_anchor.
    """
    L, h, w = 1000.0, 150.0, 200.0
    T_fl = 80_000.0  # garante touchdown grande

    r_sem = solve_with_seabed_friction(
        L=L, h=h, w=w, mu=0.0, mode=SolutionMode.TENSION, input_value=T_fl,
    )
    r_alto = solve_with_seabed_friction(
        L=L, h=h, w=w, mu=5.0, mode=SolutionMode.TENSION, input_value=T_fl,
    )
    # Geometria idêntica
    assert r_alto.total_horz_distance == pytest.approx(r_sem.total_horz_distance, rel=1e-12)
    assert r_alto.total_grounded_length == pytest.approx(r_sem.total_grounded_length, rel=1e-12)
    assert r_alto.H == pytest.approx(r_sem.H, rel=1e-12)
    # Tração na âncora deve ir a 0 com μ=5
    assert r_alto.anchor_tension == pytest.approx(0.0, abs=1e-6)
    assert r_sem.anchor_tension > 0


# ==============================================================================
# BC-02 — Catenária pura com touchdown + atrito moderado
# ==============================================================================


def test_BC02_contra_moorpy() -> None:
    """
    BC-02: catenária pura com touchdown, atrito moderado.

    O Documento A v2.2 Seção 6.2 deixa BC-02 com entradas a definir.
    Usamos os mesmos parâmetros geométricos de BC-09 (wire rope 3",
    touchdown claro) mas com μ=0,30 (atrito típico wire/argila da
    Seção 4.4). Comparação contra MoorPy com CB=0.3.
    """
    L = 700.0
    h = 300.0
    w = 13.78 * LBF_FT_TO_N_M
    mu = 0.30
    T_fl_input = 150_000.0
    EA_rigid = 1e15

    # Solver via catenary.solve_rigid_suspended (com dispatch)
    my = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl_input, mu=mu,
    )
    assert my.status == ConvergenceStatus.CONVERGED
    assert my.total_grounded_length > 0

    X_my = my.total_horz_distance
    H_my = my.H
    L_g_my = my.total_grounded_length
    T_anchor_my = my.anchor_tension

    # MoorPy com CB=μ
    fAH, fAV, fBH, fBV, info = mp_catenary(
        XF=X_my, ZF=h, L=L, EA=EA_rigid, W=w, CB=mu,
    )
    T_fl_mp = math.sqrt(fBH ** 2 + fBV ** 2)
    H_mp = abs(fBH)
    T_anchor_mp = math.sqrt(fAH ** 2 + fAV ** 2)
    LBot_mp = info.get("LBot", 0.0)

    assert T_fl_mp == pytest.approx(T_fl_input, rel=TOL_FORCE_REL)
    assert H_mp == pytest.approx(H_my, rel=TOL_FORCE_REL)
    assert LBot_mp == pytest.approx(L_g_my, rel=TOL_GROUNDED_REL)
    # T_anchor é afetado pelo atrito → comparar com maior tolerância
    # (MoorPy pode usar formulação ligeiramente diferente de friction profile)
    assert T_anchor_mp == pytest.approx(T_anchor_my, rel=5e-2)

    print(
        f"\nBC-02 (μ={mu}):"
        f"\n  X          : {X_my:.2f} m"
        f"\n  H          : my={H_my/1000:.2f} kN  MoorPy={H_mp/1000:.2f} kN"
        f"\n  L_grounded : my={L_g_my:.2f} m   MoorPy={LBot_mp:.2f} m"
        f"\n  T_anchor   : my={T_anchor_my/1000:.2f} kN  MoorPy={T_anchor_mp/1000:.2f} kN"
    )


def test_BC08_contra_moorpy() -> None:
    """
    BC-08: seabed com atrito elevado (μ=1,0).

    Parâmetros: wire rope 3" (h=300, L=700), T_fl=150 kN, μ=1,0.
    Com μ=1 e L_g ~100 m, atrito anula boa parte da tração (T_anchor
    pequeno ou zero).
    """
    L = 700.0
    h = 300.0
    w = 13.78 * LBF_FT_TO_N_M
    mu = 1.0
    T_fl_input = 150_000.0
    EA_rigid = 1e15

    my = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl_input, mu=mu,
    )
    assert my.status == ConvergenceStatus.CONVERGED

    X_my = my.total_horz_distance
    H_my = my.H
    L_g_my = my.total_grounded_length
    T_anchor_my = my.anchor_tension

    # MoorPy com CB=1.0
    fAH, fAV, fBH, fBV, info = mp_catenary(
        XF=X_my, ZF=h, L=L, EA=EA_rigid, W=w, CB=mu,
    )
    T_fl_mp = math.sqrt(fBH ** 2 + fBV ** 2)
    H_mp = abs(fBH)
    LBot_mp = info.get("LBot", 0.0)

    assert T_fl_mp == pytest.approx(T_fl_input, rel=TOL_FORCE_REL)
    assert H_mp == pytest.approx(H_my, rel=TOL_FORCE_REL)
    # Com atrito elevado, o L_g "efetivo" do MoorPy pode incluir slack;
    # geometria da touchdown ainda bate.
    assert LBot_mp == pytest.approx(L_g_my, rel=5e-2)

    print(
        f"\nBC-08 (μ={mu}):"
        f"\n  X          : {X_my:.2f} m"
        f"\n  H          : my={H_my/1000:.2f} kN  MoorPy={H_mp/1000:.2f} kN"
        f"\n  L_grounded : my={L_g_my:.2f} m   MoorPy={LBot_mp:.2f} m"
        f"\n  T_anchor   : my={T_anchor_my/1000:.2f} kN"
    )
