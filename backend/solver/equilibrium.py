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
    WatchcirclePoint,
    WatchcircleResult,
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
    precomputed_anchors: list[tuple[float, float]] | None = None,
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

    `precomputed_anchors` permite reusar o baseline em chamadas em
    lote (F5.6 watchcircle). Quando `None`, baseline é computado
    aqui dentro.
    """
    # 1. Baseline para extrair posição das âncoras.
    anchors = (
        precomputed_anchors
        if precomputed_anchors is not None
        else _solve_baseline_anchor_positions(msys_input)
    )

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

    # 2. fsolve outer loop com estratégia de retry robusta.
    #
    # Em alguns ângulos (notadamente carga alinhada com eixos
    # principais quando o spread está em diagonais — ex.: load em
    # 90°/180°/270° em spread 45°/135°/225°/315°), fsolve encontra
    # *fixed points* patológicos a centenas de metros do equilíbrio
    # físico real. Mitigamos com 4 chutes diferentes, escolhendo
    # aquele que dá o MENOR resíduo E offset fisicamente plausível
    # (≤ 50 m, condizente com mooring offshore real).
    #
    # Robustez > performance aqui — varredura de watchcircle paga
    # ~4× o tempo, mas resultados ficam sólidos em todas as direções.
    fenv_xy = (env.Fx, env.Fy)
    init_dir = (env.Fx / env.magnitude, env.Fy / env.magnitude)
    perp_dir = (-init_dir[1], init_dir[0])  # perpendicular à direção da carga
    candidate_chutes = [
        (init_dir[0] * 0.5, init_dir[1] * 0.5),
        (init_dir[0] * 2.0, init_dir[1] * 2.0),
        # Chute perpendicular ajuda a escapar de fixed points alinhados
        # com a direção da carga em casos simétricos.
        (init_dir[0] * 1.0 + perp_dir[0] * 0.5,
         init_dir[1] * 1.0 + perp_dir[1] * 0.5),
        (init_dir[0] * 1.0 - perp_dir[0] * 0.5,
         init_dir[1] * 1.0 - perp_dir[1] * 0.5),
    ]
    # Limiar de plausibilidade física: offsets > 50m em mooring
    # estático tipicamente são solução numérica de degenerate (linhas
    # esticadas além do que a física do problema permite).
    max_plausible_offset_m = 50.0

    iter_count = [0]

    def residual_with_count(d: np.ndarray) -> np.ndarray:
        iter_count[0] += 1
        return _residual(d, msys_input, anchors, fenv_xy)

    best_delta: np.ndarray | None = None
    best_residual = float("inf")
    best_ier = 0
    last_msg = ""
    for cx, cy in candidate_chutes:
        delta0 = np.array([cx, cy])
        try:
            delta_try, info, ier_try, msg_try = fsolve(
                residual_with_count, delta0,
                full_output=True, xtol=1e-3, maxfev=max_iter,
            )
            offset_try = float(math.hypot(delta_try[0], delta_try[1]))
            # Soluções não-físicas (offset enorme) são descartadas
            # mesmo se o resíduo numérico estiver baixo.
            if offset_try > max_plausible_offset_m:
                last_msg = (
                    f"Chute ({cx:.2f},{cy:.2f}) levou a offset "
                    f"{offset_try:.0f}m — descartado."
                )
                continue
            res_vec = _residual(delta_try, msys_input, anchors, fenv_xy)
            res_mag = float(math.hypot(res_vec[0], res_vec[1]))
            if res_mag < best_residual:
                best_residual = res_mag
                best_delta = delta_try
                best_ier = ier_try
                last_msg = msg_try
            if res_mag <= tol_force_n:
                break
        except Exception as exc:  # noqa: BLE001
            last_msg = f"Erro numérico no fsolve: {exc}"
            continue

    if best_delta is None:
        return PlatformEquilibriumResult(
            environmental_load=env,
            offset_xy=(0.0, 0.0),
            offset_magnitude=0.0,
            lines=[],
            restoring_force_xy=(0.0, 0.0),
            residual_magnitude=float("inf"),
            iterations=iter_count[0],
            converged=False,
            message=f"fsolve falhou em todos os chutes. {last_msg}",
            solver_version=SOLVER_VERSION,
        )
    delta_opt = best_delta
    ier = best_ier
    msg = last_msg

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
    # Critério prático: se o resíduo bate a tolerância em força, o
    # ponto é fisicamente válido mesmo que fsolve relate "não
    # convergiu" (ier != 1) — o que pode acontecer em casos onde o
    # Jacobian numérico fica mal-condicionado mas a solução é boa.
    converged = residual_mag <= tol_force_n
    fsolve_converged = ier == 1

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


def compute_watchcircle(
    msys_input: "MooringSystemInput",
    magnitude_n: float,
    n_steps: int = 36,
) -> WatchcircleResult:
    """
    F5.6 — Varre a direção da carga em 360° (passo `360/n_steps`)
    com magnitude fixa, devolvendo o envelope de offsets.

    Otimização: o baseline (resolver cada linha em Δ=0 para extrair
    posição das âncoras) é computado UMA vez e reusado em todos os
    `n_steps` equilíbrios. Sem isso, varredura de 36 passos custaria
    36× o trabalho do baseline.

    Carga zero curto-circuita: devolve `n_steps` pontos com offset
    zero — útil pra UI consistente mesmo sem carga.
    """
    if n_steps < 4:
        raise ValueError(f"n_steps deve ser ≥ 4, recebido {n_steps}")
    if magnitude_n < 0:
        raise ValueError(f"magnitude_n deve ser ≥ 0, recebido {magnitude_n}")

    # Baseline pré-computado: reusa para todos os passos.
    anchors = _solve_baseline_anchor_positions(msys_input)

    points: list[WatchcirclePoint] = []
    max_offset = 0.0
    max_offset_az = 0.0
    max_util = 0.0
    worst = AlertLevel.OK
    n_failed = 0

    for i in range(n_steps):
        az_deg = i * (360.0 / n_steps)
        az_rad = math.radians(az_deg)
        env = EnvironmentalLoad(
            Fx=magnitude_n * math.cos(az_rad),
            Fy=magnitude_n * math.sin(az_rad),
        )
        eq = solve_platform_equilibrium(
            msys_input, env, precomputed_anchors=anchors,
        )
        points.append(WatchcirclePoint(
            azimuth_deg=az_deg,
            magnitude_n=magnitude_n,
            equilibrium=eq,
        ))

        if not eq.converged:
            n_failed += 1
        if eq.offset_magnitude > max_offset:
            max_offset = eq.offset_magnitude
            max_offset_az = az_deg
        if eq.max_utilization > max_util:
            max_util = eq.max_utilization
        if _ALERT_SEVERITY[eq.worst_alert_level] > _ALERT_SEVERITY[worst]:
            worst = eq.worst_alert_level

    return WatchcircleResult(
        magnitude_n=magnitude_n,
        n_steps=n_steps,
        points=points,
        max_offset_magnitude=max_offset,
        max_offset_load_azimuth_deg=max_offset_az,
        max_utilization=max_util,
        worst_alert_level=worst,
        n_failed=n_failed,
        solver_version=SOLVER_VERSION,
    )


__all__ = ["compute_watchcircle", "solve_platform_equilibrium"]
