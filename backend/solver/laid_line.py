"""
Caso degenerado: linha 100% horizontal no seabed (drop vertical = 0).

Ocorre quando o fairlead está submerso na mesma cota da âncora (ambos no
seabed, ou ambos em uma cota intermediária com endpoint_grounded=True).
Não existe catenária; a linha é reta ao longo do seabed e a mecânica se
resume a atrito de Coulomb uniforme + alongamento elástico.

Modelo
------
Linha apoiada em toda sua extensão (L_g = L, L_s = 0). Sejam s ∈ [0, L]
medido da âncora para o fairlead.

  T(s) = T_anchor + μ · w · s
  T_fl = T_anchor + μ · w · L   (atrito soma no sentido fairlead)

O atrito se opõe ao deslocamento imposto pelo fairlead, então a tração
cai linearmente da fairlead até a âncora.

Alongamento elástico (mesma formulação global da Camada 4):
  T_mean = (T_fl + T_anchor) / 2 = T_fl − μ·w·L/2
  L_stretched = L · (1 + T_mean/EA)
  X = L_stretched  (reta apoiada no seabed)

Modos
-----
TENSION: T_fl dado. Válido se T_fl >= μ·w·L (senão atrito sozinho já
  segura a linha e a tensão não propaga até a âncora — tratamos como
  caso com slack: T_anchor = 0 e só um trecho da linha fica tracionado).

RANGE: X dado. Resolver por inversão:
  T_mean = EA · (X/L − 1)
  T_fl   = T_mean + μ·w·L/2
  T_anchor = 2·T_mean − T_fl = T_mean − μ·w·L/2
  Requer X >= L (a linha não pode ficar abaixo do unstretched) e
  T_anchor >= 0 para ser auto-consistente.
"""
from __future__ import annotations

import math

import numpy as np

from .types import (
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


def solve_laid_line(
    L: float,
    w: float,
    EA: float,
    mode: SolutionMode,
    input_value: float,
    mu: float,
    MBL: float,
    config: SolverConfig | None = None,
) -> SolverResult:
    """Solver da linha horizontal no seabed. Ver docstring do módulo."""
    if config is None:
        config = SolverConfig()
    if L <= 0 or w <= 0 or EA <= 0:
        raise ValueError("L, w, EA devem ser > 0")
    if mu < 0:
        raise ValueError("mu deve ser >= 0")

    friction = mu * w * L  # atrito total mobilizável no comprimento L

    if mode == SolutionMode.TENSION:
        T_fl = float(input_value)
        if T_fl <= 0:
            raise ValueError("T_fl deve ser > 0")
        if mu > 0 and T_fl < friction:
            # Atrito segura a linha — âncora "cega" para a tração aplicada.
            # Fisicamente: só uma porção s* = T_fl/(μ·w) da linha próxima ao
            # fairlead fica tensionada; o resto permanece em repouso (T≈0).
            # Isso é caso com slack; tratamos como inviável para evitar
            # resultados ambíguos (conceito de "âncora não reage").
            raise ValueError(
                f"T_fl={T_fl:.1f} N < atrito mobilizado μ·w·L={friction:.1f} N: "
                "a âncora nem sente a tração (linha fica parcialmente frouxa). "
                "Caso com slack no seabed — fora do escopo do solver estático."
            )
        T_anchor = T_fl - friction
    elif mode == SolutionMode.RANGE:
        X = float(input_value)
        if X <= 0:
            raise ValueError("X deve ser > 0")
        if X < L - 1e-6:
            raise ValueError(
                f"X={X:.2f} m < L={L:.2f} m: linha precisaria compactar, "
                "fisicamente impossível. Use X >= L."
            )
        strain = max(0.0, (X - L) / L)
        T_mean = EA * strain
        T_fl = T_mean + friction / 2.0
        T_anchor = T_mean - friction / 2.0
        if T_anchor < -1e-6:
            raise ValueError(
                f"Configuração incompatível: X={X:.2f} m produziria "
                f"T_anchor={T_anchor:.1f} N < 0. Aumente X ou reduza μ."
            )
        T_anchor = max(0.0, T_anchor)
    else:
        raise ValueError(f"modo desconhecido: {mode}")

    T_mean = (T_fl + T_anchor) / 2.0
    L_stretched = L * (1.0 + T_mean / EA)
    X = L_stretched  # reta no seabed

    n = config.n_plot_points
    # Discretização ao longo da linha stretched (âncora em s_phys=0, fairlead em s_phys=L).
    # Como o segmento é homogêneo e o atrito uniforme, a tração varia linear em s.
    s_phys = np.linspace(0.0, L, n)
    coords_x = (s_phys / L) * X  # reta no seabed, distribuída proporcional
    coords_y = np.zeros(n)
    tension_mag = T_anchor + (T_fl - T_anchor) * (s_phys / L)
    tension_x = tension_mag.copy()  # tudo horizontal
    tension_y = np.zeros(n)

    utilization = (T_fl / MBL) if MBL > 0 else 0.0

    return SolverResult(
        status=ConvergenceStatus.CONVERGED,
        message=(
            f"Linha horizontal no seabed (drop=0). Atrito μ·w·L="
            f"{friction:.1f} N absorvido ao longo de {L:.1f} m."
        ),
        coords_x=coords_x.tolist(),
        coords_y=coords_y.tolist(),
        tension_x=tension_x.tolist(),
        tension_y=tension_y.tolist(),
        tension_magnitude=tension_mag.tolist(),
        fairlead_tension=T_fl,
        anchor_tension=T_anchor,
        total_horz_distance=X,
        endpoint_depth=0.0,
        unstretched_length=L,
        stretched_length=L_stretched,
        elongation=L_stretched - L,
        total_suspended_length=0.0,
        total_grounded_length=L,
        dist_to_first_td=None,
        angle_wrt_horz_fairlead=0.0,  # reta no seabed
        angle_wrt_vert_fairlead=math.pi / 2.0,
        angle_wrt_horz_anchor=0.0,
        angle_wrt_vert_anchor=math.pi / 2.0,
        H=T_fl,  # toda a tração é horizontal
        iterations_used=0,
        utilization=utilization,
    )


__all__ = ["solve_laid_line"]
