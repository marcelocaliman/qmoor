"""
F5.5 — Solver de equilíbrio de plataforma sob carga ambiental.

Dada uma configuração de mooring system (N linhas com posição polar
de fairlead) e uma carga horizontal externa F_env, encontra o offset
(Δx, Δy) da plataforma tal que a soma das forças horizontais das
linhas (no novo arranjo geométrico) cancele F_env.

Estratégia:

  1. **Baseline**: cada linha é resolvida no estado neutro (Δ=0) usando
     seu boundary spec original. O X resolvido determina a posição da
     âncora no plano da plataforma (a âncora é fixada no espaço; só a
     plataforma se move).

  2. **Outer loop**: `scipy.optimize.fsolve` em duas variáveis (Δx, Δy)
     com função residual = Σ F_lines(Δ) + F_env. Tipicamente converge
     em 5–15 iterações.

  3. **Inner per-line solve**: para cada Δ, calcula nova X_i =
     ‖âncora − fairlead_novo‖ e chama o solver canônico em modo Range.
     A direção do pull é ditada pelo vetor unitário fairlead→âncora.

Limitações do MVP:

  * Mooring radial — fairleads em (R cos θ, R sin θ); sem yaw.
  * Sem rigidez de elemento (EI=0); só elástico axial via solver canônico.
  * Sem amortecimento ou inércia; só estático em equilíbrio.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Sequence

import numpy as np
from scipy.optimize import fsolve

from . import SOLVER_VERSION
from .solver import solve as solve_single_line
from .types import (
    AlertLevel,
    BoundaryConditions,
    ConvergenceStatus,
    EnvironmentalLoad,
    MooringLineResult,
    PlatformEquilibriumResult,
    SolutionMode,
)

if TYPE_CHECKING:
    from backend.api.schemas.mooring_systems import (
        MooringSystemInput,
        SystemLineSpec,
    )


# Hierarquia de severidade (replicada do multi_line.py p/ não criar
# import circular entre módulos do solver).
_ALERT_SEVERITY: dict[AlertLevel, int] = {
    AlertLevel.OK: 0,
    AlertLevel.YELLOW: 1,
    AlertLevel.RED: 2,
    AlertLevel.BROKEN: 3,
}


def _polar_to_xy(r: float, theta_rad: float) -> tuple[float, float]:
    return r * math.cos(theta_rad), r * math.sin(theta_rad)


def _solve_baseline_anchor_positions(
    msys_input: "MooringSystemInput",
) -> list[tuple[float, float]]:
    """
    Resolve o sistema no estado neutro e devolve a posição da âncora
    de cada linha no plano da plataforma. A âncora de cada linha fica
    em ((R + X_baseline) cos θ, (R + X_baseline) sin θ).

    Linhas que não convergem no baseline ficam com âncora `None` (
    representada como (NaN, NaN) no array para preservar índices).
    """
    anchors: list[tuple[float, float]] = []
    for line in msys_input.lines:
        theta = math.radians(line.fairlead_azimuth_deg)
        res = solve_single_line(
            line_segments=list(line.segments),
            boundary=line.boundary,
            seabed=line.seabed,
            criteria_profile=line.criteria_profile,
            user_limits=line.user_defined_limits,
            attachments=tuple(line.attachments),
        )
        if res.status == ConvergenceStatus.CONVERGED:
            r_anchor = line.fairlead_radius + res.total_horz_distance
            anchors.append(_polar_to_xy(r_anchor, theta))
        else:
            anchors.append((float("nan"), float("nan")))
    return anchors


def _solve_line_at_offset(
    line: "SystemLineSpec",
    anchor_xy: tuple[float, float],
    offset_xy: tuple[float, float],
) -> MooringLineResult:
    """
    Resolve uma linha individual com a plataforma deslocada de
    `offset_xy`. A âncora fica fixa em `anchor_xy`; a fairlead nova
    fica em (R_polar + Δ). X é a distância horizontal entre eles.
    """
    theta_baseline = math.radians(line.fairlead_azimuth_deg)
    fl_x = line.fairlead_radius * math.cos(theta_baseline) + offset_xy[0]
    fl_y = line.fairlead_radius * math.sin(theta_baseline) + offset_xy[1]
    dx = anchor_xy[0] - fl_x
    dy = anchor_xy[1] - fl_y
    new_X = math.hypot(dx, dy)
    # Direção fairlead → âncora (a linha exerce sobre a plataforma
    # uma força nessa direção, magnitude H).
    if new_X > 1e-9:
        cos_pull = dx / new_X
        sin_pull = dy / new_X
    else:
        cos_pull = math.cos(theta_baseline)
        sin_pull = math.sin(theta_baseline)

    # Força a linha em modo Range com o novo X. Se o usuário usou
    # Tension no input original, isso pode dar T_fl bem diferente do
    # spec — o ponto é justamente esse: equilíbrio dita as tensões.
    bc_range = BoundaryConditions(
        h=line.boundary.h,
        mode=SolutionMode.RANGE,
        input_value=new_X,
        startpoint_depth=line.boundary.startpoint_depth,
        endpoint_grounded=line.boundary.endpoint_grounded,
    )
    res = solve_single_line(
        line_segments=list(line.segments),
        boundary=bc_range,
        seabed=line.seabed,
        criteria_profile=line.criteria_profile,
        user_limits=line.user_defined_limits,
        attachments=tuple(line.attachments),
    )

    if res.status == ConvergenceStatus.CONVERGED:
        h = res.H
    else:
        h = 0.0

    return MooringLineResult(
        line_name=line.name,
        fairlead_azimuth_deg=line.fairlead_azimuth_deg,
        fairlead_radius=line.fairlead_radius,
        fairlead_xy=(fl_x, fl_y),
        anchor_xy=anchor_xy,
        horz_force_xy=(h * cos_pull, h * sin_pull),
        solver_result=res,
    )


def _residual(
    delta: np.ndarray,
    msys_input: "MooringSystemInput",
    anchors: list[tuple[float, float]],
    fenv: tuple[float, float],
) -> np.ndarray:
    """Σ F_linhas(Δ) + F_env. Em equilíbrio = 0."""
    total_x = 0.0
    total_y = 0.0
    for line, anchor in zip(msys_input.lines, anchors):
        if math.isnan(anchor[0]):
            continue  # linha que falhou no baseline — ignora no equilíbrio
        lr = _solve_line_at_offset(line, anchor, (float(delta[0]), float(delta[1])))
        total_x += lr.horz_force_xy[0]
        total_y += lr.horz_force_xy[1]
    return np.array([total_x + fenv[0], total_y + fenv[1]])


def _aggregate(
    line_results: Sequence[MooringLineResult],
) -> dict:
    fx = 0.0
    fy = 0.0
    n_converged = 0
    n_invalid = 0
    max_util = 0.0
    worst = AlertLevel.OK
    for lr in line_results:
        sr = lr.solver_result
        if sr.status == ConvergenceStatus.CONVERGED:
            fx += lr.horz_force_xy[0]
            fy += lr.horz_force_xy[1]
            n_converged += 1
            if sr.utilization > max_util:
                max_util = sr.utilization
            if (
                sr.alert_level is not None
                and _ALERT_SEVERITY[sr.alert_level] > _ALERT_SEVERITY[worst]
            ):
                worst = sr.alert_level
        else:
            n_invalid += 1
    return {
        "restoring_force_xy": (fx, fy),
        "max_utilization": max_util,
        "worst_alert_level": worst,
        "n_converged": n_converged,
        "n_invalid": n_invalid,
    }


def solve_platform_equilibrium(
    msys_input: "MooringSystemInput",
    env: EnvironmentalLoad,
    *,
    max_iter: int = 80,
    tol_force_n: float = 10.0,
) -> PlatformEquilibriumResult:
    """
    Encontra o offset da plataforma sob carga ambiental F_env e devolve
    o resultado completo (offset, tensões resultantes, agregados).

    Args:
        msys_input: configuração do mooring system
        env: carga ambiental horizontal (Fx, Fy em N)
        max_iter: limite de iterações do fsolve
        tol_force_n: tolerância no resíduo de equilíbrio em N

    Returns:
        PlatformEquilibriumResult com `converged=True` se o solver
        atingiu a tolerância. Se algumas linhas falharam no baseline,
        elas ficam fora do equilíbrio e o resíduo pode ser maior — o
        flag `converged` reflete só a convergência do fsolve.

    Carga zero curto-circuita: retorna offset (0, 0) imediatamente
    sem chamar fsolve (mais rápido e numericamente mais limpo).
    """
    # 1. Baseline para extrair posição das âncoras.
    anchors = _solve_baseline_anchor_positions(msys_input)

    # Atalho para carga zero: equilíbrio é o estado neutro.
    if env.magnitude < 1e-9:
        line_results = [
            _solve_line_at_offset(line, anchor, (0.0, 0.0))
            for line, anchor in zip(msys_input.lines, anchors)
            if not math.isnan(anchor[0])
        ]
        # Inclui linhas que falharam no baseline com anchor NaN como inválidas.
        # Para preservar contagem, re-incluímos via re-solve no offset 0.
        # Edge case raro — se baseline falha, o equilíbrio também falha.
        agg = _aggregate(line_results)
        residual_xy = (
            agg["restoring_force_xy"][0] + env.Fx,
            agg["restoring_force_xy"][1] + env.Fy,
        )
        return PlatformEquilibriumResult(
            environmental_load=env,
            offset_xy=(0.0, 0.0),
            offset_magnitude=0.0,
            offset_azimuth_deg=0.0,
            lines=line_results,
            residual_magnitude=math.hypot(*residual_xy),
            iterations=0,
            converged=True,
            message="Carga zero — offset trivial (0, 0).",
            solver_version=SOLVER_VERSION,
            **agg,
        )

    # 2. fsolve outer loop.
    # Chute inicial: pequeno deslocamento NA MESMA DIREÇÃO da F_env.
    # Convenção: a plataforma desloca no sentido da força aplicada;
    # cabos do lado oposto se estendem e geram a força restauradora
    # em sentido contrário. Ex.: carga em +X faz plataforma ir +X,
    # cabos do lado −X esticam e puxam em −X balanceando o sistema.
    # Escala 1 m é arbitrária — fsolve ajusta rapidamente.
    fenv_xy = (env.Fx, env.Fy)
    init_scale = 1.0
    init_dir = (env.Fx / env.magnitude, env.Fy / env.magnitude)
    delta0 = np.array([init_dir[0] * init_scale, init_dir[1] * init_scale])

    iter_count = [0]

    def residual_with_count(d: np.ndarray) -> np.ndarray:
        iter_count[0] += 1
        return _residual(d, msys_input, anchors, fenv_xy)

    try:
        delta_opt, info, ier, msg = fsolve(
            residual_with_count,
            delta0,
            full_output=True,
            xtol=1e-3,  # 1 mm de tolerância no offset
            maxfev=max_iter,
        )
    except Exception as exc:  # noqa: BLE001
        # fsolve raramente lança; mais comum é não convergir e
        # retornar `ier != 1`.
        return PlatformEquilibriumResult(
            environmental_load=env,
            offset_xy=(0.0, 0.0),
            offset_magnitude=0.0,
            lines=[],
            restoring_force_xy=(0.0, 0.0),
            residual_magnitude=float("inf"),
            iterations=iter_count[0],
            converged=False,
            message=f"Erro numérico no fsolve: {exc}",
            solver_version=SOLVER_VERSION,
        )

    # 3. Computa estado final no offset encontrado.
    delta_final = (float(delta_opt[0]), float(delta_opt[1]))
    line_results = [
        _solve_line_at_offset(line, anchor, delta_final)
        for line, anchor in zip(msys_input.lines, anchors)
        if not math.isnan(anchor[0])
    ]
    agg = _aggregate(line_results)
    residual_xy = (
        agg["restoring_force_xy"][0] + env.Fx,
        agg["restoring_force_xy"][1] + env.Fy,
    )
    residual_mag = math.hypot(*residual_xy)
    fsolve_converged = ier == 1
    converged = fsolve_converged and residual_mag <= tol_force_n

    offset_mag = math.hypot(*delta_final)
    if offset_mag > 1e-6:
        az_rad = math.atan2(delta_final[1], delta_final[0])
        offset_az = math.degrees(az_rad)
        if offset_az < 0:
            offset_az += 360.0
        if offset_az >= 360.0:
            offset_az -= 360.0
    else:
        offset_az = 0.0

    final_msg = (
        f"Equilíbrio em offset {offset_mag:.2f} m a "
        f"{offset_az:.1f}° (resíduo {residual_mag:.2f} N)."
    ) if converged else (
        f"Não convergiu plenamente. Resíduo {residual_mag:.2f} N "
        f"acima da tolerância {tol_force_n} N. fsolve msg: {msg}"
    )

    return PlatformEquilibriumResult(
        environmental_load=env,
        offset_xy=delta_final,
        offset_magnitude=offset_mag,
        offset_azimuth_deg=offset_az,
        lines=line_results,
        residual_magnitude=residual_mag,
        iterations=iter_count[0],
        converged=converged,
        message=final_msg,
        solver_version=SOLVER_VERSION,
        **agg,
    )


__all__ = ["solve_platform_equilibrium"]
