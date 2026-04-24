"""
Camada 1 — Catenária rígida pura (sem elasticidade, sem seabed).

Implementa a formulação geral da catenária bidimensional para linha
totalmente suspensa. A âncora pode ou não coincidir com o vértice da
catenária (i.e., V_anchor >= 0, não necessariamente V_anchor = 0).

A Seção 3.3.1 do Documento A v2.2 apresenta a formulação simplificada
"âncora no vértice" (V_anchor = 0), que é um caso particular. Aqui
implementamos a forma geral porque BC-01 e outros casos do benchmark
têm V_anchor > 0 (linha próxima do taut).

Convenção geométrica
--------------------
Âncora em (0, 0); fairlead em (X, h) com h > 0 (fairlead acima da âncora).
s = comprimento de arco medido do vértice do catenário.
A âncora está em s = s_a >= 0; o fairlead em s = s_f = s_a + L.
Quando s_a < 0 seria necessário, o caso exige touchdown no seabed —
tratado na Camada 2 (seabed.py), não aqui.

Relações fundamentais (catenária geral, vértice em s=0):
  x(s) = a · asinh(s/a)
  y(s) = sqrt(a² + s²) − a
  T(s) = w · sqrt(a² + s²)
  H = a · w         (constante no trecho suspenso)
  V(s) = w · s
  a = H / w         (parâmetro catenário)

Referências
-----------
  - Documento A v2.2, Seções 3.2, 3.3.1, 3.3.2, 3.5
  - Documentação MVP v2, Seção 7.1
"""
from __future__ import annotations

import math
from typing import Tuple

import numpy as np
from scipy.optimize import brentq

from .types import (
    BoundaryConditions,
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


# ==============================================================================
# Helpers puros da catenária (referência: vértice em s=0)
# ==============================================================================


def catenary_parameter(H: float, w: float) -> float:
    """Parâmetro catenário a = H/w (m). H em N, w em N/m."""
    if w <= 0:
        raise ValueError(f"peso submerso w deve ser > 0 (recebido {w})")
    if H <= 0:
        raise ValueError(f"tração horizontal H deve ser > 0 (recebido {H})")
    return H / w


def catenary_length(a: float, X_s: float) -> float:
    """
    Comprimento de arco da catenária do vértice (x=0) até x=X_s.

    L_s = a · sinh(X_s/a). Fórmula da Seção 3.3.1 do Documento A v2.2.
    """
    return a * math.sinh(X_s / a)


def catenary_height(a: float, X_s: float) -> float:
    """
    Altura da catenária do vértice (y=0) até x=X_s.

    h = a · (cosh(X_s/a) − 1). Fórmula da Seção 3.3.1 do Documento A v2.2.
    """
    return a * (math.cosh(X_s / a) - 1.0)


def catenary_shape(a: float, X_s: float, n: int = 101) -> Tuple[np.ndarray, np.ndarray]:
    """
    Discretiza a catenária do vértice (x=0, y=0) até x=X_s com n pontos.

    Retorna (x, y) como arrays NumPy. y(0) = 0 (vértice é origem).
    """
    if n < 2:
        raise ValueError("n deve ser >= 2")
    x = np.linspace(0.0, X_s, n)
    y = a * (np.cosh(x / a) - 1.0)
    return x, y


# ==============================================================================
# Solver de catenária rígida, totalmente suspensa (caso geral)
# ==============================================================================


def _solve_suspended_tension_mode(
    L: float, h: float, w: float, T_fl: float
) -> dict:
    """
    Caso totalmente suspenso, modo Tension: T_fl dado, achar X e geometria.

    Closed-form (sem iteração). Derivação:
      R_f = T(s_f)/w = T_fl/w
      R_a = T(s_a)/w = R_f − h             (de h = R_f − R_a)
      R_f² − R_a² = s_f² − s_a² = L·(s_a + s_f)  (identidade)
        ⇒ s_a = (R_f² − R_a² − L²) / (2·L)
      a² = R_a² − s_a²

    Levanta ValueError se solução exige touchdown (s_a < 0) ou se caso
    é fisicamente inválido (T_fl insuficiente ou a² negativo).
    """
    if T_fl <= w * h:
        raise ValueError(
            f"T_fl={T_fl:.1f} N insuficiente para sustentar peso suspenso "
            f"w·h={w * h:.1f} N (caso inválido: linha não atinge o fairlead)"
        )

    R_f = T_fl / w
    R_a = R_f - h  # > 0 garantido pelo teste acima

    s_a = (R_f * R_f - R_a * R_a - L * L) / (2.0 * L)
    if s_a < -1e-9:
        # Solução suspensa teria vértice "além" da âncora → precisa de touchdown
        raise ValueError(
            f"T_fl={T_fl:.1f} N abaixo da tração crítica para totalmente suspenso: "
            f"caso demanda touchdown (s_a={s_a:.2f} < 0)"
        )
    s_a = max(s_a, 0.0)  # limpa ruído numérico para o caso crítico

    a_sq = R_a * R_a - s_a * s_a
    if a_sq <= 0:
        raise ValueError(
            f"a² = {a_sq:.3e} <= 0: caso numericamente inválido "
            "(linha perfeitamente taut ou dados inconsistentes)"
        )
    a = math.sqrt(a_sq)
    s_f = s_a + L
    H = a * w

    # Distância horizontal entre anchor e fairlead:
    # X = x(s_f) − x(s_a) = a · [asinh(s_f/a) − asinh(s_a/a)]
    X = a * (math.asinh(s_f / a) - math.asinh(s_a / a))

    return {
        "a": a,
        "H": H,
        "s_a": s_a,
        "s_f": s_f,
        "X": X,
        "T_fl": T_fl,
        "T_anchor": w * R_a,
        "V_anchor": w * s_a,
        "V_fairlead": w * s_f,
    }


def _s_a_from_h_given_a(a: float, L: float, h: float) -> float:
    """
    Para dado parâmetro a e comprimento L, resolve a equação da altura
    h = sqrt(a² + (s+L)²) − sqrt(a² + s²) para s = s_a >= 0.

    Usa brentq. Retorna 0 exatamente se a solução seria ligeiramente
    negativa (caso crítico ancora-no-vértice).
    """

    def f(s: float) -> float:
        return math.sqrt(a * a + (s + L) ** 2) - math.sqrt(a * a + s * s) - h

    # f é estritamente crescente em s (f'(s) = (s+L)/√… − s/√… > 0 para L>0).
    # f(0) = √(a²+L²) − a − h. f(∞) → L − h.
    f0 = f(0.0)
    if f0 >= 0.0:
        return 0.0  # caso crítico / touchdown latente
    if L <= h:
        raise ValueError(
            f"L={L:.2f} <= h={h:.2f}: linha mais curta que a lâmina d'água, "
            "fairlead inalcançável"
        )
    # Como f é crescente e f(∞) = L − h > 0, existe zero em (0, algum s_hi).
    s_hi = max(L, h) * 2.0
    while f(s_hi) < 0.0:
        s_hi *= 2.0
        if s_hi > 1e12:
            raise ValueError("busca por s_a divergiu")
    return brentq(f, 0.0, s_hi, xtol=1e-9, rtol=1e-12, maxiter=200)


def _solve_suspended_range_mode(
    L: float, h: float, w: float, X: float, config: SolverConfig
) -> dict:
    """
    Caso totalmente suspenso, modo Range: X dado, achar T_fl e geometria.

    Busca unidimensional no parâmetro a (equivalente a busca em H = a·w):
      para cada a, resolve h → s_a, e checa se X(a, s_a) bate com X dado.

    Bracket em a:
      - a → 0⁺:   X → 0 (linha dobra verticalmente)
      - a → ∞:    X → sqrt(L² − h²) (linha taut; forma reta)
    Se X_input >= sqrt(L²−h²), caso fisicamente impossível (linha não
    estica no modelo rígido).
    """
    X_max_rigid = math.sqrt(L * L - h * h)
    if X >= X_max_rigid - 1e-9:
        raise ValueError(
            f"X={X:.2f} ≥ X_max={X_max_rigid:.2f} (= √(L²−h²)): linha rígida "
            "não alcança; precisa de elasticidade ou caso é inválido"
        )

    def X_of_a(a: float) -> float:
        s_a = _s_a_from_h_given_a(a, L, h)
        s_f = s_a + L
        return a * (math.asinh(s_f / a) - math.asinh(s_a / a))

    def residual(a: float) -> float:
        return X_of_a(a) - X

    # Bracket: a_lo pequeno o suficiente para X_of_a(a_lo) < X;
    # a_hi grande o suficiente para X_of_a(a_hi) > X.
    a_lo = 1e-3
    a_hi = 10.0 * max(L, h)
    # Expandir a_hi se necessário
    while residual(a_hi) < 0.0:
        a_hi *= 10.0
        if a_hi > 1e18:
            raise RuntimeError("não consegui limitar a_hi em mode Range")
    a = brentq(
        residual, a_lo, a_hi,
        xtol=1e-6, rtol=1e-10, maxiter=config.max_brent_iter,
    )
    s_a = _s_a_from_h_given_a(a, L, h)
    s_f = s_a + L
    H = a * w
    T_fl = w * math.sqrt(a * a + s_f * s_f)
    T_anchor = w * math.sqrt(a * a + s_a * s_a)

    return {
        "a": a,
        "H": H,
        "s_a": s_a,
        "s_f": s_f,
        "X": X,
        "T_fl": T_fl,
        "T_anchor": T_anchor,
        "V_anchor": w * s_a,
        "V_fairlead": w * s_f,
    }


# ==============================================================================
# Construção do SolverResult a partir da solução interna
# ==============================================================================


def _build_result(
    sol: dict, L: float, h: float, w: float, config: SolverConfig, MBL: float = 0.0
) -> SolverResult:
    """Transforma o dicionário interno da solução em SolverResult completo."""
    a: float = sol["a"]
    s_a: float = sol["s_a"]
    s_f: float = sol["s_f"]
    H: float = sol["H"]
    X: float = sol["X"]
    T_fl: float = sol["T_fl"]
    T_anchor: float = sol["T_anchor"]

    # Discretização: n pontos equi-espaçados em arco não-esticado de anchor (s_phys=0)
    # até fairlead (s_phys=L). Para cada ponto, s_cat = s_a + s_phys.
    n = config.n_plot_points
    s_phys = np.linspace(0.0, L, n)
    s_cat = s_a + s_phys

    # Posições físicas em relação à âncora em (0, 0):
    # x(s_cat) − x(s_a) = a·(asinh(s_cat/a) − asinh(s_a/a))
    # y(s_cat) − y(s_a) = sqrt(a²+s_cat²) − sqrt(a²+s_a²)
    coords_x = a * (np.arcsinh(s_cat / a) - math.asinh(s_a / a))
    coords_y = np.sqrt(a * a + s_cat * s_cat) - math.sqrt(a * a + s_a * s_a)

    # Componentes de tração:
    # T_horz (magnitude) = H em todo s; T_vert = w·s_cat (positivo puxando para cima);
    # Componente signada de T_horz no sistema global aponta de fairlead para âncora;
    # para simplicidade e compatibilidade com Seção 6 (arrays), exportamos magnitudes
    # T(s) = w·sqrt(a² + s²).
    tension_x = np.full(n, H)
    tension_y = w * s_cat
    tension_mag = np.sqrt(tension_x * tension_x + tension_y * tension_y)

    # Ângulos no fairlead e na âncora (com horizontal e vertical, em rad):
    # tan(theta_wrt_horz) = V/H
    theta_h_fl = math.atan2(w * s_f, H)
    theta_v_fl = math.pi / 2.0 - theta_h_fl
    theta_h_a = math.atan2(w * s_a, H)
    theta_v_a = math.pi / 2.0 - theta_h_a

    utilization = (T_fl / MBL) if MBL > 0 else 0.0

    return SolverResult(
        status=ConvergenceStatus.CONVERGED,
        message="Catenária rígida totalmente suspensa (Camada 1).",
        coords_x=coords_x.tolist(),
        coords_y=coords_y.tolist(),
        tension_x=tension_x.tolist(),
        tension_y=tension_y.tolist(),
        tension_magnitude=tension_mag.tolist(),
        fairlead_tension=T_fl,
        anchor_tension=T_anchor,
        total_horz_distance=X,
        endpoint_depth=h,
        unstretched_length=L,
        stretched_length=L,  # camada 1: rígido, sem alongamento
        elongation=0.0,
        total_suspended_length=L,  # tudo suspenso
        total_grounded_length=0.0,
        dist_to_first_td=None,
        angle_wrt_horz_fairlead=theta_h_fl,
        angle_wrt_vert_fairlead=theta_v_fl,
        angle_wrt_horz_anchor=theta_h_a,
        angle_wrt_vert_anchor=theta_v_a,
        H=H,
        iterations_used=0,
        utilization=utilization,
    )


# ==============================================================================
# Entry point público da Camada 1
# ==============================================================================


def solve_rigid_suspended(
    L: float,
    h: float,
    w: float,
    mode: SolutionMode,
    input_value: float,
    config: SolverConfig | None = None,
    MBL: float = 0.0,
) -> SolverResult:
    """
    Resolve catenária rígida, totalmente suspensa, nos dois modos.

    Parâmetros
    ----------
    L : comprimento não-esticado da linha (m).
    h : distância vertical âncora → fairlead (m).
    w : peso submerso por unidade de comprimento (N/m).
    mode : SolutionMode.TENSION ou SolutionMode.RANGE.
    input_value : T_fl (N) se mode=Tension; X (m) se mode=Range.
    config : SolverConfig — tolerâncias e max iter.
    MBL : opcional, apenas para preencher `utilization` no resultado.

    Levanta ValueError se o caso exigir touchdown ou for fisicamente
    inválido. As camadas posteriores (seabed, friction) interceptam
    esses casos e despacham para as formulações apropriadas.
    """
    if config is None:
        config = SolverConfig()

    if mode == SolutionMode.TENSION:
        sol = _solve_suspended_tension_mode(L, h, w, input_value)
    elif mode == SolutionMode.RANGE:
        sol = _solve_suspended_range_mode(L, h, w, input_value, config)
    else:
        raise ValueError(f"modo desconhecido: {mode}")

    return _build_result(sol, L, h, w, config, MBL=MBL)


__all__ = [
    "catenary_parameter",
    "catenary_length",
    "catenary_height",
    "catenary_shape",
    "solve_rigid_suspended",
]
