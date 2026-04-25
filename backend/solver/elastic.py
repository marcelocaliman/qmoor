"""
Camada 4 — Correção elástica da catenária.

Modelo: cada elemento estica segundo
  dL_stretched = dL_unstretched · (1 + T_média / EA)

conforme Seção 3.3.2 do Documento A v2.2 (decisão fechada: "tração axial
média do elemento, não tração local, por estabilidade numérica em malha
grosseira").

Como temos UMA linha (um segmento homogêneo) no MVP v1, aplica-se uma
T_média global:
  L_stretched = L_unstretched · (1 + T_média_global / EA)

O ponto fixo da iteração é
  F(L_eff) = L_eff − L · (1 + T_mean(L_eff)/EA) = 0

Resolvido por brentq (mais robusto que iteração ponto-fixo, que diverge
em casos de linha muito taut onde L_eff está próximo de √(X²+h²)).

Região viável
-------------
- Mode Range: L_eff > √(X²+h²) (senão linha não alcança X) e L_eff < X+h
  (senão cai em caso patológico com slack no seabed; Camada 7).
- Mode Tension: L_eff ≥ L_s(T_fl) (senão L_g < 0; tratado no solver rígido
  via dispatch, mas para T_fl ≤ w·h o caso é genuinamente inviável).

Referências:
  - Documento A v2.2, Seções 3.3.2, 3.5.3
  - Documentação MVP v2, Seção 7.3
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.optimize import brentq

from .catenary import solve_rigid_suspended
from .types import (
    ConvergenceStatus,
    SolutionMode,
    SolverConfig,
    SolverResult,
)


def _mean_tension(result: SolverResult) -> float:
    """Tração média ao longo da linha (média aritmética sobre discretização)."""
    return float(np.mean(result.tension_magnitude))


def apply_elastic_correction(
    unstretched_length: float, EA: float, T_mean: float
) -> float:
    """
    Retorna L_stretched = L · (1 + T_mean / EA), conforme Seção 3.3.2.
    """
    if EA <= 0:
        raise ValueError("EA deve ser > 0 no modo elástico")
    return unstretched_length * (1.0 + T_mean / EA)


def _solve_rigid_for_elastic(
    L_eff: float,
    *,
    h: float,
    w: float,
    mode: SolutionMode,
    input_value: float,
    mu: float,
    config: SolverConfig,
    MBL: float,
) -> Optional[SolverResult]:
    """Chama solve_rigid_suspended, retornando None se o caso é inviável
    geometricamente para o L_eff dado (mas não necessariamente inválido
    fisicamente)."""
    try:
        return solve_rigid_suspended(
            L=L_eff, h=h, w=w, mode=mode, input_value=input_value,
            config=config, mu=mu, MBL=MBL,
        )
    except ValueError:
        return None


def solve_elastic_iterative(
    L: float,
    h: float,
    w: float,
    EA: float,
    mode: SolutionMode,
    input_value: float,
    config: SolverConfig | None = None,
    mu: float = 0.0,
    MBL: float = 0.0,
) -> SolverResult:
    """Solver completo com correção elástica. Ver docstring do módulo."""
    if config is None:
        config = SolverConfig()
    if EA <= 0:
        raise ValueError("EA deve ser > 0 no modo elástico")

    # Pre-check de validade física (Seção 8 do MVP v2 PDF)
    if mode == SolutionMode.TENSION:
        T_fl = float(input_value)
        if T_fl <= w * h:
            raise ValueError(
                f"T_fl={T_fl:.1f} N <= w·h={w * h:.1f} N: "
                "linha não sustenta a coluna d'água até o fairlead (caso inviável)."
            )

    # Construção do bracket para brentq
    if mode == SolutionMode.RANGE:
        X_target = float(input_value)
        L_taut = math.sqrt(X_target * X_target + h * h)
        # Mínimo geométrico: linha precisa estar acima do taut.
        L_lo = max(L, L_taut) * 1.0001
        # Máximo viável: L_eff < X + h; além disso cai em caso com slack.
        L_hi_cap = (X_target + h) * 0.9999
    else:
        L_lo = L
        # Tensão: sem limite superior rígido; usamos 100×L como teto seguro.
        L_hi_cap = L * 100.0

    # Verifica se L_lo é viável geometricamente. _cache guarda o último
    # resultado bem-sucedido; _call_count conta quantas avaliações de F
    # ocorreram (incluindo expansão de bracket e iterações do brentq).
    _cache: dict = {"L_eff": None, "result": None, "T_mean": None}
    _call_count: list[int] = [0]

    def F(L_eff: float) -> float:
        _call_count[0] += 1
        r = _solve_rigid_for_elastic(
            L_eff, h=h, w=w, mode=mode, input_value=input_value,
            mu=mu, config=config, MBL=MBL,
        )
        if r is None:
            return -1e12  # sinaliza infeasível geometricamente (L_eff curto)
        T_mean = _mean_tension(r)
        _cache["L_eff"] = L_eff
        _cache["result"] = r
        _cache["T_mean"] = T_mean
        return L_eff - L * (1.0 + T_mean / EA)

    f_lo = F(L_lo)
    if f_lo <= -1e11:
        raise ValueError(
            f"Caso geometricamente inviável: solver rígido falha mesmo no "
            f"L_eff mínimo ({L_lo:.1f} m). Parâmetros impossíveis para linha elástica."
        )

    # Encontra L_hi com F > 0 (dentro do cap)
    if f_lo > 0:
        # L_lo já satisfaz — raro; usa diretamente (linha praticamente rígida)
        L_eff_final = L_lo
    else:
        L_hi = min(L_hi_cap, max(L_lo, L) * 2.0)
        for _ in range(30):
            f_hi = F(L_hi)
            if f_hi > 0:
                break
            if L_hi >= L_hi_cap * 0.99999:
                # Esgotamos a região viável sem achar F > 0.
                # O ponto fixo exigiria L_eff > L_hi_cap (caso com slack).
                raise ValueError(
                    f"Caso ill-conditioned: o equilíbrio exigiria L_eff > "
                    f"L_eff_max = {L_hi_cap:.1f} m (limite físico da formulação). "
                    "Provavelmente é caso com slack no seabed — fora do escopo da Camada 4."
                )
            L_hi = min(L_hi * 1.5, L_hi_cap)
        else:
            raise ValueError("Não foi possível construir bracket para brentq.")

        L_eff_final = brentq(
            F, L_lo, L_hi,
            xtol=max(L * config.elastic_tolerance, 1e-6),
            rtol=config.elastic_tolerance,
            maxiter=config.max_brent_iter,
        )

    # Garante que o cache tem o resultado para L_eff_final
    if _cache["L_eff"] != L_eff_final:
        F(L_eff_final)
    rigid_result = _cache["result"]
    assert rigid_result is not None

    # iterations_used = nº de avaliações de F durante expansão de bracket
    # + brentq + eventuais re-avaliações. Reflete o custo real do solver.
    iters = _call_count[0]

    # Sanidade física: aço/poliéster operacional opera com strain < 1%; mesmo
    # poliéster em deformação aparente raramente passa de 3-4%. Strains acima
    # de 5% indicam que algum dos inputs (EA, T_fl, w) está em unidade errada
    # ou irrealista. Sinalizamos como caso inviável com mensagem explicativa.
    strain = (L_eff_final - L) / L
    if strain > 0.05:
        raise ValueError(
            f"Strain final {strain * 100:.1f}% (>5%) é fisicamente implausível. "
            "Provável input em unidade errada — verifique se EA está em "
            "Newtons (não te/tonne-força) e w em N/m (não kgf/m). Para wire/"
            "chain reais, strain operacional < 1%."
        )

    return SolverResult(
        **{
            **rigid_result.model_dump(),
            "status": ConvergenceStatus.CONVERGED,
            "unstretched_length": L,
            "stretched_length": L_eff_final,
            "elongation": L_eff_final - L,
            "iterations_used": iters,
            "message": (
                f"Catenária elástica convergida (L_stretched={L_eff_final:.3f} m, "
                f"elongação {strain * 100:.2f}%)."
            ),
        }
    )


__all__ = [
    "apply_elastic_correction",
    "solve_elastic_iterative",
]
