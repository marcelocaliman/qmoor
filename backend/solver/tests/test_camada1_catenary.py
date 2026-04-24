"""
Testes da Camada 1 — Catenária rígida pura.

Cobre: helpers (catenary_parameter, catenary_length/height/shape), consistência
inversa, e benchmark BC-01 contra MoorPy (linha totalmente suspensa, sem
touchdown, sem elasticidade).
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from moorpy.Catenary import catenary as mp_catenary

from backend.solver.catenary import (
    catenary_height,
    catenary_length,
    catenary_parameter,
    catenary_shape,
    solve_rigid_suspended,
)
from backend.solver.types import (
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
)


# Tolerâncias de aprovação contra MoorPy, conforme Seção 6.3 do Documento A v2.2
TOL_GEOM_REL = 5e-3  # 0,5% em geometria
TOL_FORCE_REL = 1e-2  # 1% em forças

# Constante física
LBF_FT_TO_N_M = 14.593903  # 1 lbf/ft em N/m (força por comprimento)

# ==============================================================================
# Helpers puros
# ==============================================================================


def test_catenary_parameter_basico() -> None:
    """a = H/w com valores conhecidos."""
    assert catenary_parameter(1000.0, 10.0) == pytest.approx(100.0)
    assert catenary_parameter(5.0e5, 200.0) == pytest.approx(2500.0)


def test_catenary_parameter_recusa_valores_invalidos() -> None:
    with pytest.raises(ValueError):
        catenary_parameter(H=-1.0, w=10.0)
    with pytest.raises(ValueError):
        catenary_parameter(H=100.0, w=0.0)


def test_catenary_length_formula() -> None:
    """L_s = a·sinh(X_s/a) — bate com identidade hiperbólica."""
    a = 100.0
    X_s = 50.0
    # Computa e compara com sinh direto
    assert catenary_length(a, X_s) == pytest.approx(a * math.sinh(X_s / a))
    # Caso especial: X_s pequeno → L_s ≈ X_s (linha quase reta perto do vértice)
    X_small = 1.0
    assert catenary_length(a, X_small) == pytest.approx(X_small, rel=1e-3)


def test_catenary_height_formula() -> None:
    """h = a·(cosh(X_s/a) − 1)."""
    a = 100.0
    X_s = 50.0
    assert catenary_height(a, X_s) == pytest.approx(a * (math.cosh(X_s / a) - 1.0))


def test_catenary_shape_simetria() -> None:
    """Forma é função par em x (embora discretizemos só x >= 0)."""
    a = 50.0
    X_s = 40.0
    x, y = catenary_shape(a, X_s, n=21)
    # y(0) = 0 (vértice na origem)
    assert y[0] == pytest.approx(0.0, abs=1e-12)
    # y monotonicamente crescente em x
    assert np.all(np.diff(y) > 0)
    # Último ponto bate com catenary_height
    assert y[-1] == pytest.approx(catenary_height(a, X_s))


def test_catenary_consistencia_inversa() -> None:
    """
    Dado a, X_s: calcula L_s, h. Reconstrói X_s a partir de a e L_s
    (X_s = a·asinh(L_s/a)). Deve recuperar X_s original dentro da tolerância.
    """
    a = 150.0
    X_s = 80.0
    L_s = catenary_length(a, X_s)
    h = catenary_height(a, X_s)
    # Inversão: X_s = a·asinh(L_s/a)
    X_s_recovered = a * math.asinh(L_s / a)
    assert X_s_recovered == pytest.approx(X_s, rel=1e-12)
    # Também: h = a·(cosh(X_s/a) - 1) == sqrt(a²+L_s²) - a (identidade)
    h_from_L = math.sqrt(a * a + L_s * L_s) - a
    assert h == pytest.approx(h_from_L, rel=1e-12)


# ==============================================================================
# Solver de linha totalmente suspensa
# ==============================================================================


def test_solve_tension_mode_recusa_T_fl_insuficiente() -> None:
    """T_fl <= w·h → caso inválido (não sustenta peso)."""
    with pytest.raises(ValueError, match="insuficiente"):
        solve_rigid_suspended(
            L=100.0, h=50.0, w=100.0,
            mode=SolutionMode.TENSION, input_value=4000.0,  # < w·h = 5000
        )


def test_solve_tension_mode_detecta_necessidade_touchdown() -> None:
    """
    T_fl baixa o suficiente para que a solução suspensa teria s_a < 0
    (vértice "além" da âncora). Camada 1 deve levantar ValueError — a
    Camada 2 (seabed) é quem trata esses casos.
    """
    # Caso artificial: L grande demais para ser totalmente suspenso com o T_fl dado
    with pytest.raises(ValueError, match="touchdown"):
        solve_rigid_suspended(
            L=1000.0, h=100.0, w=100.0,
            mode=SolutionMode.TENSION, input_value=15000.0,
        )


def test_solve_tension_range_sao_consistentes() -> None:
    """
    Resolve modo Tension com T_fl, obtém X; resolve modo Range com esse X;
    deve recuperar T_fl original.
    """
    L = 450.0
    h = 300.0
    w = 13.78 * LBF_FT_TO_N_M  # ~201.1 N/m
    T_fl_in = 785_000.0

    result_t = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl_in,
    )
    X_out = result_t.total_horz_distance

    result_r = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.RANGE, input_value=X_out,
    )
    T_fl_recovered = result_r.fairlead_tension

    assert T_fl_recovered == pytest.approx(T_fl_in, rel=TOL_FORCE_REL / 10.0)


# ==============================================================================
# BC-01 — Catenária pura suspensa (Documento A v2.2, Seção 6.1.1)
# ==============================================================================


def test_BC01_contra_moorpy() -> None:
    """
    BC-01: Lâmina 300 m, L=450 m, wire 3 in, w=13.78 lbf/ft (~201 N/m),
           T_fl=785 kN. Sem touchdown (linha totalmente suspensa).

    Validação: meu solver com T_fl=785 kN deve dar X tal que MoorPy nesse X
    também retorne T_fl ≈ 785 kN. Tolerâncias: 0,5% geometria, 1% força.
    """
    L = 450.0
    h = 300.0
    w = 13.78 * LBF_FT_TO_N_M
    T_fl_input = 785_000.0
    EA_rigid = 1e15  # valor alto para aproximar MoorPy-rígido

    # Minha solução
    my = solve_rigid_suspended(
        L=L, h=h, w=w, mode=SolutionMode.TENSION, input_value=T_fl_input,
    )
    assert my.status == ConvergenceStatus.CONVERGED
    X_my = my.total_horz_distance
    H_my = my.H
    T_anchor_my = my.anchor_tension

    # MoorPy no mesmo X
    fAH, fAV, fBH, fBV, info = mp_catenary(
        XF=X_my, ZF=h, L=L, EA=EA_rigid, W=w, CB=0,
    )
    T_fl_mp = math.sqrt(fBH ** 2 + fBV ** 2)
    T_anchor_mp = math.sqrt(fAH ** 2 + fAV ** 2)
    H_mp = abs(fBH)  # MoorPy retorna signado; magnitude horizontal
    LBot_mp = info.get("LBot", 0.0)

    # Deve ser totalmente suspenso
    assert LBot_mp == pytest.approx(0.0, abs=1e-3), (
        f"MoorPy detectou {LBot_mp} m no seabed; BC-01 espera zero"
    )

    # Força no fairlead: meu T_fl de input vs T_fl computado pelo MoorPy ao meu X
    assert T_fl_mp == pytest.approx(T_fl_input, rel=TOL_FORCE_REL), (
        f"T_fl MoorPy={T_fl_mp:.1f} N vs input={T_fl_input:.1f} N, "
        f"desvio rel {abs(T_fl_mp - T_fl_input) / T_fl_input:.4%}"
    )

    # Tração horizontal: comparação direta
    assert H_mp == pytest.approx(H_my, rel=TOL_FORCE_REL)

    # Tração na âncora: comparação
    assert T_anchor_mp == pytest.approx(T_anchor_my, rel=TOL_FORCE_REL)

    # Coordenadas discretizadas devem cobrir do (0,0) ao (X, h)
    assert my.coords_x[0] == pytest.approx(0.0, abs=1e-6)
    assert my.coords_y[0] == pytest.approx(0.0, abs=1e-6)
    assert my.coords_x[-1] == pytest.approx(X_my, rel=1e-9)
    assert my.coords_y[-1] == pytest.approx(h, rel=TOL_GEOM_REL)

    # Informacional: imprime resumo do comparativo para log do pytest
    print(
        f"\nBC-01 comparativo:"
        f"\n  X           : my={X_my:.3f} m"
        f"\n  H (horz T)  : my={H_my/1000:.3f} kN   MoorPy={H_mp/1000:.3f} kN"
        f"\n  T_fl        : input={T_fl_input/1000:.3f} kN  MoorPy={T_fl_mp/1000:.3f} kN"
        f"\n  T_anchor    : my={T_anchor_my/1000:.3f} kN   MoorPy={T_anchor_mp/1000:.3f} kN"
    )
