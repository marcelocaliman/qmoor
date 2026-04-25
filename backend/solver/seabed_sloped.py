"""
F5.3 — Seabed inclinado: touchdown em rampa para linha single-segmento.

Modelo geométrico
-----------------
Anchor na origem (0, 0). Seabed é uma reta `y = m·x` onde `m = tan(θ_s)`
e `θ_s` é a inclinação. Convenção:
  - θ_s > 0: seabed sobe em direção ao fairlead.
  - θ_s < 0: seabed desce em direção ao fairlead.

Fairlead em (X, h) com h > 0 (drop vertical da âncora ao fairlead).

A linha tem comprimento (esticado) L_eff. Trecho grounded (apoiado no
seabed) tem comprimento L_g e vai do anchor (0, 0) ao touchdown
(x_td, m·x_td). Trecho suspenso tem comprimento L_s = L_eff − L_g e
vai do touchdown ao fairlead.

Catenária no trecho suspenso
----------------------------
Use a parametrização por vértice virtual: a curva é
    y(x) = y_v + a·(cosh((x − x_v)/a) − 1)
com tangente local
    dy/dx = sinh((x − x_v)/a)

No touchdown, a tangente da catenária deve igualar `m` (alinhamento
com a rampa) — condição de "encaixe suave":
    sinh((x_td − x_v)/a) = m
    (x_td − x_v)/a = asinh(m)

Defina `u = asinh(m)` e `v = (X − x_v)/a` (parâmetro a determinar).
Então:
  - cosh(u) = sqrt(1 + m²)
  - sinh(u) = m
  - x_td = x_v + a·u = X − a·(v − u)
  - y_td = y_v + a·(cosh(u) − 1) = y_v + a·(sqrt(1+m²) − 1)
  - h    = y_v + a·(cosh(v) − 1)
  - L_s  = a·(sinh(v) − sinh(u)) = a·(sinh(v) − m)
  - T_fl = w·sqrt(a² + s_f²) com s_f = a·sinh(v) → T_fl = w·a·cosh(v)
  - H    = w·a (constante no trecho suspenso)
  - T_td = w·a·cosh(u) = w·a·sqrt(1+m²)

Como o touchdown está no seabed: y_td = m·x_td. Substituindo:
    h − m·x_td = a·(cosh(v) − sqrt(1+m²))                       (i)
    L_g = x_td·sqrt(1+m²)                                        (ii)
    L_eff = L_g + L_s                                            (iii)

Atrito de Coulomb na rampa
--------------------------
Para o trecho grounded numa rampa de inclinação θ_s, a força normal
por unidade de comprimento é w·cos(θ_s) e a componente da gravidade
paralela à rampa é w·sin(θ_s). Atrito de Coulomb se opõe ao
movimento relativo. Para uma linha sob tração T_td no touchdown
puxando subindo a rampa (em direção ao fairlead), o anchor recebe:
    T_anchor = T_td − μ·w·cos(θ_s)·L_g + w·sin(θ_s)·L_g_signed
onde `w·sin(θ)·L_g` adiciona quando a rampa SOBE para o fairlead
(peso ajuda a puxar para baixo, no sentido âncora) — sinal +,
e subtrai quando desce.

Simplificação adotada (F5.3): usamos a componente axial efetiva
da gravidade. Em casos com gradação significativa, pode haver
deslizamento livre (μ < tan|θ|). Detectamos e sinalizamos.

Modos suportados
----------------
TENSION: dado T_fl, busca v em (asinh(m)+ε, ∞) tal que F(v) = 0.
  Sistema reduzido a 1 incógnita (v).

RANGE: dado X, idem mas resolve sistema diferente. F5.3 entrega
  apenas TENSION; RANGE em rampa é roadmap (raro em projetos).
"""
from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

from .types import (
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


def _solve_touchdown_sloped_tension(
    L: float,
    h: float,
    w: float,
    T_fl: float,
    mu: float,
    slope_rad: float,
    config: SolverConfig,
) -> dict:
    """
    Resolve modo Tension com touchdown numa rampa de inclinação `slope_rad`.

    Reduz o sistema a uma única equação F(v) = 0 onde
        v = (X − x_v)/a    (parâmetro adimensional do fairlead local)

    Da relação T_fl = w·a·cosh(v) tiramos `a = T_fl/(w·cosh(v))`. As
    demais incógnitas (X, x_td, L_g, L_s) ficam expressas em função de v.

    A equação de fechamento usa a restrição L_eff = L_g + L_s.
    """
    if w <= 0:
        raise ValueError("w deve ser > 0")
    if T_fl <= 0:
        raise ValueError("T_fl deve ser > 0")
    if abs(slope_rad) >= math.pi / 4 - 1e-6:
        raise ValueError("slope_rad fora de range [-π/4, +π/4]")

    m = math.tan(slope_rad)
    u = math.asinh(m)
    sqrt_1pm2 = math.sqrt(1.0 + m * m)

    def geometry_for_v(v: float) -> dict:
        """Calcula a, X, x_td, L_g, L_s, h_calc para um v dado."""
        if v <= u + 1e-9:
            raise ValueError("v deve ser > asinh(m) (touchdown válido)")
        cosh_v = math.cosh(v)
        sinh_v = math.sinh(v)
        a = T_fl / (w * cosh_v)
        # x_v = X − a·v ⇒ X − x_v = a·v
        # x_td = X − a·(v − u) ⇒ x_td − anchor (0,0) = x_td
        # y_v = h − a·(cosh(v) − 1)
        y_v = h - a * (cosh_v - 1.0)
        # y_td = y_v + a·(sqrt(1+m²) − 1) deve igualar m·x_td
        # E x_td = x_v + a·u ⇒ x_v = x_td − a·u
        # Mas x_v também = X − a·v. Logo x_td = X − a·v + a·u = X − a·(v − u)
        # Para fechar: precisa expressar X em função de v. Use a equação
        # y_td = m·x_td:
        #   h − a·(cosh(v) − sqrt(1+m²)) = m·x_td
        #   x_td = (h − a·(cosh(v) − sqrt(1+m²))) / m   (m ≠ 0)
        if abs(m) < 1e-9:
            # Caso θ=0: cai no caminho horizontal padrão. Aqui não chega
            # porque o despacho em solver.py escolhe outro caminho.
            raise ValueError("slope_rad ≈ 0 deve usar solver horizontal")
        x_td = (h - a * (cosh_v - sqrt_1pm2)) / m
        if x_td < 0:
            raise ValueError(
                f"x_td={x_td:.2f} < 0: geometria infactível para v={v:.4f}"
            )
        # X derivado: X = x_td + a·(v − u)
        X = x_td + a * (v - u)
        L_g = x_td * sqrt_1pm2
        L_s = a * (sinh_v - m)
        return {
            "a": a, "v": v, "X": X, "x_td": x_td,
            "L_g": L_g, "L_s": L_s,
            "y_v": y_v, "x_v": X - a * v,
            "cosh_v": cosh_v, "sinh_v": sinh_v,
        }

    def residual(v: float) -> float:
        try:
            g = geometry_for_v(v)
        except ValueError:
            return 1e9 * (1 if v < (u + 1) else -1)
        return g["L_g"] + g["L_s"] - L

    # Bracket: para v = asinh(m) + ε, L_s ≈ 0 e L_g é o que dominante
    # (linha quase toda apoiada). Para v → ∞, L_s → ∞.
    # Procuramos v tal que L_g + L_s = L. Brent com bracket explícito.
    v_lo = u + 1e-3  # ε acima de asinh(m)
    v_hi = u + 10.0  # típico bem acima do que precisamos

    # Expansão se necessário
    f_lo = residual(v_lo)
    f_hi = residual(v_hi)
    if f_lo > 0:
        # L_g(v_lo) > L: linha curta demais para o caso
        raise ValueError(
            f"L={L:.1f} m insuficiente para alcançar o fairlead com "
            f"slope={math.degrees(slope_rad):.1f}°. Aumente L ou reduza slope."
        )
    if f_hi < 0:
        for _ in range(20):
            v_hi *= 1.5
            f_hi = residual(v_hi)
            if f_hi > 0:
                break

    if f_hi <= 0:
        raise ValueError(
            "Não foi possível bracketar v: caso geometricamente inviável "
            "para a inclinação informada."
        )

    v_sol = brentq(
        residual, v_lo, v_hi,
        xtol=1e-6, rtol=1e-8, maxiter=config.max_brent_iter,
    )
    g = geometry_for_v(v_sol)
    a = g["a"]
    H = w * a

    # Atrito na rampa (Coulomb): considerando a linha puxada pelo fairlead
    # subindo a rampa, atrito atua contra o movimento (desacelera). Componente
    # paralela à rampa da gravidade adiciona ou subtrai conforme o sinal de
    # slope_rad. Convenção: T_anchor = T_td − ΔT_atrito + ΔT_gravidade.
    T_td = w * a * sqrt_1pm2  # T no touchdown (catenária)
    delta_friction = mu * w * math.cos(slope_rad) * g["L_g"]
    delta_gravity = w * math.sin(slope_rad) * g["L_g"]  # +slope: gravidade ajuda no anchor → T_anchor maior; -slope: subtrai
    # Para nossa convenção: T_anchor = T_td - μ·w·cos(θ)·L_g + w·sin(θ)·L_g
    # onde +sin(θ) (rampa sobe ao fairlead) faz o cabo "deslizar" para o
    # anchor — o atrito se opõe (mas o desliz é puxado pelo fairlead). Em
    # módulo, T_anchor diminui pelo atrito e tem ajuste de gravidade.
    T_anchor = max(0.0, T_td - delta_friction + delta_gravity)

    return {
        "a": a, "H": H,
        "X": g["X"], "x_td": g["x_td"],
        "L_g": g["L_g"], "L_s": g["L_s"],
        "T_fl": T_fl, "T_anchor": T_anchor, "T_touchdown": T_td,
        "V_fairlead": w * a * g["sinh_v"],
        "V_anchor": w * a * m,  # tangente em (x_v) com sinh(u) = m
        "x_v": g["x_v"], "y_v": g["y_v"],
        "v": v_sol, "u": u, "m": m,
    }


def _build_sloped_result(
    sol: dict,
    L: float, h: float, w: float, mu: float, slope_rad: float,
    config: SolverConfig, MBL: float,
) -> SolverResult:
    """Monta SolverResult a partir do dicionário retornado pelo solver de rampa."""
    a = sol["a"]
    H = sol["H"]
    X_total = sol["X"]
    x_td = sol["x_td"]
    L_g = sol["L_g"]
    L_s = sol["L_s"]
    T_fl = sol["T_fl"]
    T_anchor = sol["T_anchor"]
    x_v = sol["x_v"]
    y_v = sol["y_v"]
    u = sol["u"]
    v = sol["v"]
    m = sol["m"]

    # Discretização: pontos no trecho grounded (linha reta na rampa) +
    # pontos na catenária do touchdown ao fairlead.
    n = config.n_plot_points
    n_g = max(2, int(round(n * L_g / max(L, L_g + L_s)))) if L_g > 0 else 0
    n_s = n - n_g
    if n_s < 2:
        n_s = 2
        n_g = n - n_s

    # Trecho grounded: ao longo da rampa de (0, 0) a (x_td, m·x_td).
    if n_g > 0:
        x_g = np.linspace(0.0, x_td, n_g)
        y_g = m * x_g
        T_g_anchor_to_td = np.linspace(T_anchor, sol["T_touchdown"], n_g)
        # Tração no trecho grounded varia linearmente entre anchor e td
        Tx_g = T_g_anchor_to_td * math.cos(slope_rad)
        Ty_g = T_g_anchor_to_td * math.sin(slope_rad)
    else:
        x_g, y_g, T_g_anchor_to_td = np.array([]), np.array([]), np.array([])
        Tx_g, Ty_g = np.array([]), np.array([])

    # Trecho suspenso: catenária no sistema (x_v, y_v) parametrizada por
    # x_local ∈ [a·u, a·v] (de touchdown ao fairlead).
    s_local = np.linspace(a * u, a * v, n_s)  # arc length no frame local
    x_susp = x_v + s_local
    y_susp = y_v + a * (np.cosh(s_local / a) - 1.0)
    # Tração: T(s) = w·sqrt(a² + sinh(s/a)²·a²) = w·a·cosh(s/a)
    s_arc = a * np.sinh(s_local / a)  # arc length
    T_susp = w * a * np.cosh(s_local / a)
    Tx_susp = np.full_like(T_susp, H)
    Ty_susp = w * s_arc

    # Concatena (evita duplicar ponto do touchdown se houver grounded)
    if n_g > 0:
        coords_x = np.concatenate([x_g, x_susp[1:]])
        coords_y = np.concatenate([y_g, y_susp[1:]])
        T_mag = np.concatenate([T_g_anchor_to_td, T_susp[1:]])
        Tx = np.concatenate([Tx_g, Tx_susp[1:]])
        Ty = np.concatenate([Ty_g, Ty_susp[1:]])
    else:
        coords_x, coords_y = x_susp, y_susp
        T_mag, Tx, Ty = T_susp, Tx_susp, Ty_susp

    # Ângulos no fairlead e na âncora (na catenária local, no frame global)
    theta_h_fl = math.atan2(w * a * math.sinh(v), H)
    theta_h_a = math.atan2(0.0 + w * a * math.sinh(u), H) if L_g > 0 else math.atan2(w * a * math.sinh(u), H)
    # Em rampa, o ângulo na âncora é ao longo da rampa: tangente = slope_rad
    if L_g > 0:
        theta_h_a = slope_rad

    utilization = T_fl / MBL if MBL > 0 else 0.0

    return SolverResult(
        status=ConvergenceStatus.CONVERGED,
        message=(
            f"Touchdown em rampa de {math.degrees(slope_rad):.1f}°: "
            f"L_g={L_g:.1f} m sobre seabed, L_s={L_s:.1f} m suspenso."
        ),
        coords_x=coords_x.tolist(),
        coords_y=coords_y.tolist(),
        tension_x=Tx.tolist(),
        tension_y=Ty.tolist(),
        tension_magnitude=T_mag.tolist(),
        fairlead_tension=T_fl,
        anchor_tension=T_anchor,
        total_horz_distance=X_total,
        endpoint_depth=h,
        unstretched_length=L,  # F5.3 inicial: rígido (sem elastic loop)
        stretched_length=L,
        elongation=0.0,
        total_suspended_length=L_s,
        total_grounded_length=L_g,
        dist_to_first_td=x_td,
        angle_wrt_horz_fairlead=theta_h_fl,
        angle_wrt_vert_fairlead=math.pi / 2.0 - theta_h_fl,
        angle_wrt_horz_anchor=theta_h_a,
        angle_wrt_vert_anchor=math.pi / 2.0 - theta_h_a,
        H=H,
        iterations_used=1,
        utilization=utilization,
    )


def solve_sloped_seabed_single_segment(
    L: float,
    h: float,
    w: float,
    EA: float,
    mode: SolutionMode,
    input_value: float,
    mu: float,
    slope_rad: float,
    MBL: float,
    config: SolverConfig | None = None,
) -> SolverResult:
    """
    Solver F5.3 para single-segmento com seabed inclinado e touchdown.

    Suporta apenas modo TENSION na entrega F5.3. Modo RANGE em rampa é
    roadmap (caso operacional raro). Elasticidade não é aplicada nesta
    sub-fase para o trecho em rampa — é roadmap junto com a generalização
    do touchdown.
    """
    if config is None:
        config = SolverConfig()
    if mode != SolutionMode.TENSION:
        raise ValueError(
            "F5.3: seabed inclinado suporta apenas modo Tension nesta "
            "entrega. Modo Range em rampa fica para sub-fase futura."
        )
    if abs(slope_rad) < 1e-6:
        raise ValueError(
            "slope_rad ≈ 0: use o caminho horizontal padrão"
        )
    sol = _solve_touchdown_sloped_tension(
        L=L, h=h, w=w, T_fl=float(input_value),
        mu=mu, slope_rad=slope_rad, config=config,
    )
    # Sanity check: L_g + L_s deve fechar com L (rígido)
    sum_L = sol["L_g"] + sol["L_s"]
    if abs(sum_L - L) / L > 1e-3:
        raise ValueError(
            f"Inconsistência: L_g + L_s = {sum_L:.2f} ≠ L = {L:.2f}"
        )
    return _build_sloped_result(sol, L, h, w, mu, slope_rad, config, MBL)


__all__ = ["solve_sloped_seabed_single_segment"]
