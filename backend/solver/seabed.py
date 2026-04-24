"""
Camada 2 — Contato com seabed sem atrito (μ=0).

Trata o caso onde a catenária "quer" ter s_a < 0 (vértice virtualmente
além da âncora), o que significa que há um trecho de linha apoiado no
seabed (grounded). No seabed plano e sem atrito:

  - o ponto de touchdown é o vértice da catenária suspensa (V=0 ali)
  - H (componente horizontal) é constante em todo o trecho suspenso
    **e** no trecho grounded (sem atrito, a linha apenas transmite
    a tração horizontal)
  - T_anchor = T_touchdown = H (sem perda por atrito)

Convenção geométrica:
  Âncora em (0, 0), touchdown em (L_g, 0) ao longo do seabed, fairlead
  em (L_g + X_s, h). L_g = L − L_s é o comprimento apoiado.

Referências:
  - Documento A v2.2, Seções 3.3.3, 3.5
  - Documentação MVP v2, Seção 7.2
"""
from __future__ import annotations

import math
from typing import Tuple

import numpy as np
from scipy.optimize import brentq

from .types import (
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


# ==============================================================================
# Helpers do touchdown
# ==============================================================================


def find_touchdown(a: float, w: float, h: float) -> Tuple[float, float]:
    """
    Dado o parâmetro catenário a e a altura h da fairlead acima do
    touchdown, retorna (X_s, L_s) do trecho suspenso:

      X_s = a · acosh(1 + h/a)       (horizontal entre touchdown e fairlead)
      L_s = a · sinh(X_s/a)          (comprimento de arco do trecho suspenso)

    Parâmetro `w` é aceito por consistência de assinatura com o resto do
    pacote (não é usado diretamente aqui — a relação é puramente geométrica).
    """
    del w  # não utilizado: assinatura por uniformidade
    if a <= 0:
        raise ValueError("a deve ser > 0")
    if h < 0:
        raise ValueError("h deve ser >= 0")
    if h == 0:
        return 0.0, 0.0
    X_s = a * math.acosh(1.0 + h / a)
    L_s = a * math.sinh(X_s / a)
    return X_s, L_s


# ==============================================================================
# Transição suspensa ↔ touchdown: valores críticos
# ==============================================================================


def critical_tension_for_touchdown(L: float, h: float, w: float) -> float:
    """
    T_fl crítico tal que s_a = 0 exatamente (âncora no vértice).

    Para T_fl >= T_fl_crit: linha totalmente suspensa (V_anchor > 0).
    Para T_fl < T_fl_crit: há touchdown (grounded segment).

    Derivação: s_a=0 ⇒ R_a = a ⇒ a + h = R_f = sqrt(a² + L²)
      ⇒ (a+h)² = a² + L²  ⇒  2ah + h² = L²  ⇒  a = (L² − h²)/(2h)
      Então T_fl_crit = w·R_f = w·sqrt(a² + L²) = w·(h² + L²)/(2h).
    """
    return w * (h * h + L * L) / (2.0 * h)


def critical_range_for_touchdown(L: float, h: float) -> float:
    """
    X_total crítico tal que s_a = 0 (transição suspenso ↔ touchdown).

    Para X_total >= X_crit: totalmente suspenso.
    Para X_total < X_crit: há touchdown.
    """
    a_crit = (L * L - h * h) / (2.0 * h)
    return a_crit * math.asinh(L / a_crit)


# ==============================================================================
# Casos com touchdown (μ=0)
# ==============================================================================


def _touchdown_tension_mode(L: float, h: float, w: float, T_fl: float, mu: float) -> dict:
    """
    Touchdown, Mode Tension: T_fl dado, resolve geometria e L_g.

    Relação-chave: T_fl = H + w·h   (tração no fairlead = H no vértice +
    ganho de peso de coluna w·h até o fairlead). Daí H, a, X_s, L_s, L_g.
    """
    H = T_fl - w * h
    if H <= 0:
        raise ValueError(
            f"T_fl={T_fl:.1f} N <= w·h={w * h:.1f} N: linha não atinge fairlead"
        )
    a = H / w
    X_s, L_s = find_touchdown(a, w, h)
    L_g = L - L_s
    if L_g < -1e-6:
        raise ValueError(
            f"L_g = L − L_s = {L_g:.3f} < 0: caso não é touchdown (dispatch falhou)"
        )
    L_g = max(0.0, L_g)
    X_total = L_g + X_s
    T_touchdown = H
    T_anchor = max(0.0, T_touchdown - mu * w * L_g)

    return {
        "a": a,
        "H": H,
        "X_s": X_s,
        "L_s": L_s,
        "L_g": L_g,
        "X_total": X_total,
        "T_fl": T_fl,
        "T_touchdown": T_touchdown,
        "T_anchor": T_anchor,
        "V_fairlead": w * L_s,
        "s_a_virtual": 0.0,  # vértice no touchdown
    }


def _touchdown_range_mode(
    L: float, h: float, w: float, X_total: float, mu: float, config: SolverConfig
) -> dict:
    """
    Touchdown, Mode Range: X_total dado, resolve a, H, T_fl.

    Parametrizando por u = X_s/a, o sistema
      h = a·(cosh(u) − 1)        (eq. altura)
      L − X_total = L_s − X_s = a·(sinh(u) − u)   (eq. "excesso de arco")
    reduz a uma única equação unidimensional em u:
      h·(sinh(u) − u) / (cosh(u) − 1) = L − X_total
    """
    LmX = L - X_total
    if LmX <= 1e-9:
        raise ValueError(f"L ({L}) <= X_total ({X_total}): caso não é touchdown")
    if LmX >= h - 1e-9:
        raise ValueError(
            f"L − X_total = {LmX:.2f} >= h = {h:.2f}: geometria inviável para touchdown"
        )

    def residual(u: float) -> float:
        # Para u pequeno, use expansão Taylor para evitar 0/0:
        #   sinh(u) − u ≈ u³/6;   cosh(u) − 1 ≈ u²/2;   razão ≈ u/3
        if u < 1e-4:
            razao = u / 3.0
        else:
            razao = (math.sinh(u) - u) / (math.cosh(u) - 1.0)
        return h * razao - LmX

    # residual(0+) = -LmX < 0; residual(∞) → h − LmX > 0. Unique zero.
    u = brentq(
        residual, 1e-8, 50.0,
        xtol=1e-10, rtol=1e-12, maxiter=config.max_brent_iter,
    )
    a = h / (math.cosh(u) - 1.0)
    X_s = a * u
    L_s = a * math.sinh(u)
    L_g = L - L_s
    H = a * w
    T_fl = w * math.sqrt(a * a + L_s * L_s)  # = H + w·h
    T_touchdown = H
    T_anchor = max(0.0, T_touchdown - mu * w * L_g)

    return {
        "a": a,
        "H": H,
        "X_s": X_s,
        "L_s": L_s,
        "L_g": L_g,
        "X_total": X_total,
        "T_fl": T_fl,
        "T_touchdown": T_touchdown,
        "T_anchor": T_anchor,
        "V_fairlead": w * L_s,
        "s_a_virtual": 0.0,
    }


# ==============================================================================
# Construção do SolverResult com grounded + suspended
# ==============================================================================


def _build_touchdown_result(
    sol: dict, L: float, h: float, w: float, mu: float, config: SolverConfig,
    MBL: float = 0.0,
) -> SolverResult:
    """Monta SolverResult para caso com touchdown."""
    a: float = sol["a"]
    H: float = sol["H"]
    X_s: float = sol["X_s"]
    L_s: float = sol["L_s"]
    L_g: float = sol["L_g"]
    X_total: float = sol["X_total"]
    T_fl: float = sol["T_fl"]
    T_anchor: float = sol["T_anchor"]
    T_touchdown: float = sol["T_touchdown"]

    # Distribuição de pontos: proporcional ao comprimento físico de cada trecho
    n = config.n_plot_points
    n_g = max(2, int(round(n * L_g / L))) if L_g > 0 else 1
    n_s = n - n_g + 1  # +1 porque o touchdown é ponto compartilhado
    n_s = max(2, n_s)

    # Grounded: âncora (0,0) → touchdown (L_g, 0)
    if L_g > 0:
        s_g = np.linspace(0.0, L_g, n_g)
        coords_x_g = s_g
        coords_y_g = np.zeros_like(s_g)
    else:
        coords_x_g = np.array([0.0])
        coords_y_g = np.array([0.0])

    # Suspenso: touchdown (L_g, 0) → fairlead (L_g + X_s, h), com vértice = touchdown
    # s_cat = comprimento de arco do vértice (touchdown) até o ponto
    s_cat_s = np.linspace(0.0, L_s, n_s)
    # Posição relativa ao touchdown: x_rel = a·asinh(s_cat/a), y_rel = sqrt(a²+s²) − a
    coords_x_s = L_g + a * np.arcsinh(s_cat_s / a)
    coords_y_s = np.sqrt(a * a + s_cat_s * s_cat_s) - a

    # Concatena, descartando o touchdown duplicado (último do grounded == primeiro do suspended)
    if L_g > 0:
        coords_x = np.concatenate([coords_x_g[:-1], coords_x_s])
        coords_y = np.concatenate([coords_y_g[:-1], coords_y_s])
    else:
        coords_x = coords_x_s
        coords_y = coords_y_s

    # Tensão:
    # Grounded sem atrito: T = H constante. Com atrito (μ>0): T cresce linearmente
    # da âncora ao touchdown. Se H − μ·w·L_g < 0, há porção slack com T=0.
    tension_x_list = []
    tension_y_list = []

    if L_g > 0:
        if mu == 0 or T_anchor > 0:
            # Linear: T(s_anchor) vai de T_anchor a H ao longo do grounded
            T_g = np.linspace(T_anchor, H, n_g)
        else:
            # Slack + stretched: T=0 até s_zero = L_g − H/(μ·w), depois cresce linearmente até H
            s_zero = L_g - H / (mu * w)
            s_g_loc = np.linspace(0.0, L_g, n_g)
            T_g = np.where(
                s_g_loc < s_zero,
                0.0,
                mu * w * (s_g_loc - s_zero),
            )
        # Na região grounded, toda tração é horizontal (no seabed); T_y = 0
        T_x_g = T_g  # magnitude horizontal = tração total no grounded
        T_y_g = np.zeros_like(T_g)
        tension_x_list.append(T_x_g[:-1])
        tension_y_list.append(T_y_g[:-1])

    # Suspended: T_x = H constante, T_y = w·s_cat, |T| = sqrt(H² + (w·s_cat)²)
    T_x_s = np.full(n_s, H)
    T_y_s = w * s_cat_s
    tension_x_list.append(T_x_s)
    tension_y_list.append(T_y_s)

    tension_x = np.concatenate(tension_x_list) if L_g > 0 else T_x_s
    tension_y = np.concatenate(tension_y_list) if L_g > 0 else T_y_s
    tension_mag = np.sqrt(tension_x * tension_x + tension_y * tension_y)

    # Ângulos
    V_fl = w * L_s
    theta_h_fl = math.atan2(V_fl, H)
    theta_v_fl = math.pi / 2.0 - theta_h_fl
    # Na âncora: se grounded, ângulo é 0 (linha horizontal).
    if L_g > 0:
        theta_h_a = 0.0
    else:
        # Caso crítico s_a = 0: âncora também no vértice → horizontal
        theta_h_a = 0.0
    theta_v_a = math.pi / 2.0 - theta_h_a

    utilization = (T_fl / MBL) if MBL > 0 else 0.0

    return SolverResult(
        status=ConvergenceStatus.CONVERGED,
        message=("Catenária rígida com touchdown, μ=0." if mu == 0
                 else f"Catenária rígida com touchdown e atrito μ={mu:.3f}."),
        coords_x=coords_x.tolist(),
        coords_y=coords_y.tolist(),
        tension_x=tension_x.tolist(),
        tension_y=tension_y.tolist(),
        tension_magnitude=tension_mag.tolist(),
        fairlead_tension=T_fl,
        anchor_tension=T_anchor,
        total_horz_distance=X_total,
        endpoint_depth=h,
        unstretched_length=L,
        stretched_length=L,  # rígido
        elongation=0.0,
        total_suspended_length=L_s,
        total_grounded_length=L_g,
        dist_to_first_td=L_g,  # horizontal da âncora até o touchdown
        angle_wrt_horz_fairlead=theta_h_fl,
        angle_wrt_vert_fairlead=theta_v_fl,
        angle_wrt_horz_anchor=theta_h_a,
        angle_wrt_vert_anchor=math.pi / 2.0 - theta_h_a,
        H=H,
        iterations_used=0,
        utilization=utilization,
    )


# ==============================================================================
# Entry point público da Camada 2
# ==============================================================================


def solve_with_seabed_no_friction(
    L: float,
    h: float,
    w: float,
    mode: SolutionMode,
    input_value: float,
    config: SolverConfig | None = None,
    MBL: float = 0.0,
) -> SolverResult:
    """
    Resolve catenária com touchdown no seabed, SEM atrito (μ=0).

    Esta função assume que o caso TEM touchdown. O dispatch (escolher
    entre suspensa e touchdown) fica em solve_rigid_suspended (catenary.py).
    """
    if config is None:
        config = SolverConfig()

    mu = 0.0
    if mode == SolutionMode.TENSION:
        sol = _touchdown_tension_mode(L, h, w, input_value, mu)
    elif mode == SolutionMode.RANGE:
        sol = _touchdown_range_mode(L, h, w, input_value, mu, config)
    else:
        raise ValueError(f"modo desconhecido: {mode}")
    return _build_touchdown_result(sol, L, h, w, mu, config, MBL=MBL)


__all__ = [
    "find_touchdown",
    "critical_tension_for_touchdown",
    "critical_range_for_touchdown",
    "solve_with_seabed_no_friction",
]
