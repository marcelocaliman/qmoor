"""
Camada 3 — Atrito de Coulomb axial no trecho apoiado.

A Seção 3.3.3 do Documento A v2.2 define o modelo:
  T(s) = T_touchdown − μ·w·(s − s_touchdown)     (decresce linearmente)
  T_anchor = max(0, T_touchdown − μ·w·L_g)

Se a tração chega a zero antes da âncora, o comprimento restante fica
frouxo no seabed (slack admissível).

Obs.: o atrito NÃO afeta a geometria do trecho suspenso (H e a catenária
no ar são idênticos aos da Camada 2). Por isso este módulo é basicamente
uma fachada sobre seabed.solve_with_seabed(..., mu>0), mais a função
helper apply_seabed_friction() que expõe o perfil de tração no grounded.

Referências:
  - Documento A v2.2, Seções 3.3.3, 4.4
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from .seabed import solve_with_seabed
from .types import SolutionMode, SolverConfig, SolverResult


class SeabedFrictionProfile(NamedTuple):
    """Perfil de tração ao longo do trecho apoiado."""

    s: np.ndarray  # coordenada de arco da âncora ao touchdown (m)
    T: np.ndarray  # tração no seabed (N)
    T_anchor: float  # tração efetiva na âncora (N)
    s_slack: float  # comprimento frouxo (com T=0) junto à âncora (m); 0 se não houver


def apply_seabed_friction(
    T_touchdown: float, w: float, mu: float, L_g: float, n: int = 51
) -> SeabedFrictionProfile:
    """
    Calcula o perfil de tração no trecho apoiado.

    Parâmetros
    ----------
    T_touchdown : tração na transição suspensa → apoiada (N). Em μ=0 esta
                  é igual à tração horizontal H do trecho suspenso.
    w : peso submerso por unidade de comprimento (N/m).
    mu : coeficiente de atrito axial de Coulomb (adimensional, >= 0).
    L_g : comprimento do trecho apoiado (m, >= 0).
    n : número de pontos na discretização (>= 2).

    Retorna
    -------
    SeabedFrictionProfile contendo:
      s : coord de arco da âncora (s=0) ao touchdown (s=L_g), crescente.
      T : tração correspondente (N).
      T_anchor : T(s=0), já com clamp >= 0.
      s_slack : se μ·w·L_g > T_touchdown, o trecho [0, s_slack] está
                frouxo (T=0). Caso contrário s_slack=0.
    """
    if mu < 0:
        raise ValueError("μ deve ser >= 0")
    if L_g < 0:
        raise ValueError("L_g deve ser >= 0")
    if n < 2:
        raise ValueError("n deve ser >= 2")

    s = np.linspace(0.0, L_g, n)  # da âncora (0) ao touchdown (L_g)
    if L_g == 0.0 or mu == 0.0:
        # Sem atrito ou sem grounded: T constante no trecho.
        T = np.full(n, T_touchdown)
        return SeabedFrictionProfile(
            s=s, T=T, T_anchor=T_touchdown, s_slack=0.0,
        )

    # T(s) = T_touchdown − μ·w·(L_g − s)  (cresce da âncora até o touchdown)
    T_linear = T_touchdown - mu * w * (L_g - s)

    # Se parte do trecho ficaria com T < 0, clampa em 0 e marca como slack
    if T_linear[0] < 0:
        s_slack = L_g - T_touchdown / (mu * w)
        T = np.where(s < s_slack, 0.0, mu * w * (s - s_slack))
        T_anchor = 0.0
    else:
        T = T_linear
        T_anchor = T_linear[0]
        s_slack = 0.0

    return SeabedFrictionProfile(s=s, T=T, T_anchor=T_anchor, s_slack=s_slack)


def solve_with_seabed_friction(
    L: float,
    h: float,
    w: float,
    mu: float,
    mode: SolutionMode,
    input_value: float,
    config: SolverConfig | None = None,
    MBL: float = 0.0,
) -> SolverResult:
    """
    Solver completo com atrito de Coulomb e touchdown no seabed.

    Delega para seabed.solve_with_seabed, que já é parametrizada por μ.
    Existe para tornar explícita a capability "com atrito" na API pública.
    """
    return solve_with_seabed(
        L, h, w, mode, input_value, mu=mu, config=config, MBL=MBL,
    )


__all__ = ["SeabedFrictionProfile", "apply_seabed_friction", "solve_with_seabed_friction"]
