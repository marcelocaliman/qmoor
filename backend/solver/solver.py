"""
Camada 5/6 — Fachada pública do solver QMoor.

Unifica todas as camadas anteriores (catenária rígida, seabed no-friction,
atrito de Coulomb, correção elástica) em uma única função de entrada que
aceita as estruturas Pydantic de alto nível:

  solve(line_segments, boundary, seabed, config, criteria_profile, user_limits)
    -> SolverResult

Despacha para solve_elastic_iterative, que por sua vez usa o dispatch
rígido-suspenso vs touchdown em solve_rigid_suspended.

O MVP v1 suporta UMA linha homogênea (um LineSegment). Multi-segmento
fica para v2.1 conforme Seção 9 do Documento A v2.2.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence

from . import SOLVER_VERSION
from .attachment_resolver import resolve_attachments
from .elastic import solve_elastic_iterative
from .laid_line import solve_laid_line
from .multi_segment import solve_multi_segment
from .seabed_sloped import solve_sloped_seabed_single_segment
from .types import (
    PROFILE_LIMITS,
    AlertLevel,
    BoundaryConditions,
    ConvergenceStatus,
    CriteriaProfile,
    LineAttachment,
    LineSegment,
    SeabedConfig,
    SolutionMode,
    SolverConfig,
    SolverResult,
    UtilizationLimits,
    classify_utilization,
)


def _validate_inputs(
    line_segments: Sequence[LineSegment],
    boundary: BoundaryConditions,
    seabed: SeabedConfig,
    config: SolverConfig,
) -> LineSegment:
    """Valida entradas e retorna o segmento único (MVP v1)."""
    if not line_segments:
        raise ValueError("line_segments vazia: forneça pelo menos um segmento")
    # Validação por segmento (Pydantic já garante >0, redundância barata).
    for i, s in enumerate(line_segments):
        if s.length <= 0 or s.EA <= 0 or s.MBL <= 0 or s.w <= 0:
            raise ValueError(
                f"segmento {i} com grandeza não-positiva (validado também por Pydantic)"
            )
    # Despacho single vs multi acontece em solve(): aqui retornamos o
    # primeiro segmento como conveniência para o caso single (mantém o
    # contrato anterior de _validate_inputs).
    segment = line_segments[0]
    if boundary.h <= 0:
        raise ValueError("lâmina d'água h deve ser > 0")
    if boundary.input_value <= 0:
        raise ValueError("input_value (T_fl ou X) deve ser > 0")
    if seabed.mu < 0:
        raise ValueError("coeficiente de atrito μ deve ser >= 0")
    # Validações específicas por modo (Seção 8 do MVP v2 PDF):
    if boundary.mode not in (SolutionMode.TENSION, SolutionMode.RANGE):
        raise ValueError(f"modo inválido: {boundary.mode}")
    # Âncora livre do seabed ainda não é suportada (requer modelagem distinta).
    if not boundary.endpoint_grounded:
        raise NotImplementedError(
            "endpoint_grounded=False (âncora elevada do seabed) não é suportado "
            "ainda. Forneça endpoint_grounded=True."
        )
    # Fairlead afundado (startpoint_depth > 0) é permitido: o drop vertical
    # efetivo usado pelo solver é h − startpoint_depth. O despacho em solve()
    # trata o caso degenerado drop = 0 (linha horizontal no seabed).
    if boundary.startpoint_depth >= boundary.h + 1e-9:
        raise ValueError(
            f"startpoint_depth={boundary.startpoint_depth:.2f} m >= "
            f"h={boundary.h:.2f} m: fairlead no ou abaixo do seabed é inviável "
            "(a âncora precisa ficar abaixo do fairlead, ou no mesmo nível)."
        )
    return segment


def _broken_ratio(
    profile: CriteriaProfile, user_limits: Optional[UtilizationLimits]
) -> float:
    """Helper: broken_ratio efetivo do perfil corrente (para mensagens)."""
    if profile == CriteriaProfile.USER_DEFINED and user_limits is not None:
        return user_limits.broken_ratio
    return PROFILE_LIMITS[profile].broken_ratio


def solve(
    line_segments: Sequence[LineSegment],
    boundary: BoundaryConditions,
    seabed: SeabedConfig | None = None,
    config: SolverConfig | None = None,
    criteria_profile: CriteriaProfile = CriteriaProfile.MVP_PRELIMINARY,
    user_limits: Optional[UtilizationLimits] = None,
    attachments: Sequence[LineAttachment] = (),
) -> SolverResult:
    """
    Executa o solver completo para uma linha isolada.

    Parâmetros
    ----------
    line_segments : lista com UM LineSegment (MVP v1 é homogêneo).
    boundary : condições de contorno (h, modo, input_value).
    seabed : configuração do seabed (μ). Default μ=0.
    config : tolerâncias e max iter. Default SolverConfig().
    criteria_profile : perfil de classificação T_fl/MBL (Seção 5 Documento A).
                       Default MVP_Preliminary (0.50 yellow / 0.60 red / 1.00 broken).
    user_limits : obrigatório se criteria_profile == USER_DEFINED.

    Retorna
    -------
    SolverResult — todos os campos da Seção 6 do MVP v2, incluindo
    status de convergência, geometria, tensões, ângulos, utilization
    e `alert_level` (ok | yellow | red | broken).

    Em caso de erro de validação ou caso fisicamente impossível, captura
    a exceção e devolve um SolverResult com status=INVALID_CASE e mensagem
    descritiva (em vez de propagar).
    """
    if seabed is None:
        seabed = SeabedConfig()
    if config is None:
        config = SolverConfig()

    try:
        segment = _validate_inputs(line_segments, boundary, seabed, config)
    except (ValueError, NotImplementedError) as exc:
        return SolverResult(
            status=ConvergenceStatus.INVALID_CASE,
            message=f"Validação falhou: {exc}",
            water_depth=boundary.h,
            startpoint_depth=boundary.startpoint_depth,
            solver_version=SOLVER_VERSION,
        )

    # F5.4.6a — Resolve attachments com posição contínua.
    # Pré-processador divide o segmento que contém um
    # `position_s_from_anchor` em dois sub-segmentos idênticos, virando
    # o attachment numa "junção virtual". O solver downstream nunca sabe
    # que houve split. Attachments via `position_index` (legacy) passam
    # intactos.
    try:
        resolved_segments, resolved_attachments = resolve_attachments(
            line_segments, attachments,
        )
    except ValueError as exc:
        return SolverResult(
            status=ConvergenceStatus.INVALID_CASE,
            message=f"Attachment inválido: {exc}",
            water_depth=boundary.h,
            startpoint_depth=boundary.startpoint_depth,
            solver_version=SOLVER_VERSION,
        )

    # Drop vertical efetivo: distância entre a âncora (no seabed, y=-h)
    # e o fairlead (submerso a profundidade startpoint_depth da superfície).
    # Quando startpoint_depth = 0 (fairlead na superfície), drop = h.
    h_drop = boundary.h - boundary.startpoint_depth

    try:
        n_segments = len(resolved_segments)
        slope = seabed.slope_rad
        slope_is_significant = abs(slope) > 1e-6

        # F5.3.y: attachments + slope agora suportados via integrador
        # com grounded estendido para aplicar saltos em V nas junções.
        if n_segments > 1 or resolved_attachments:
            # Linha composta heterogênea (F5.1) ou com attachments (F5.2).
            # F5.4.6a: para ter ≥ 2 segmentos pós-resolver, ou o usuário
            # já passou multi-segmento, ou usou `position_s_from_anchor`
            # que disparou split. Attachment com `position_index` em
            # linha de 1 segmento não faz sentido (pego pelo Pydantic
            # range validator com max_position_index = N-2).
            result = solve_multi_segment(
                segments=resolved_segments,
                h=h_drop,
                mode=boundary.mode,
                input_value=boundary.input_value,
                mu=seabed.mu,
                config=config,
                attachments=resolved_attachments,
                slope_rad=slope,
            )
        elif slope_is_significant:
            # F5.3 completa: single-segmento em rampa.
            #
            # Despacho:
            # - Fully-suspended (T_fl ≥ T_crit_horizontal): linha não toca
            #   o seabed; cálculo idêntico ao horizontal.
            # - Touchdown (T_fl < T_crit_horizontal): solver específico
            #   `solve_sloped_seabed_single_segment` com atrito modificado
            #   na rampa.
            from .seabed import (
                critical_range_for_touchdown,
                critical_tension_for_touchdown,
            )

            if boundary.mode == SolutionMode.TENSION:
                T_crit = critical_tension_for_touchdown(
                    segment.length, h_drop, segment.w,
                )
                if boundary.input_value >= T_crit:
                    # Fully suspended: usa solver horizontal (slope só visual)
                    result = solve_elastic_iterative(
                        L=segment.length, h=h_drop, w=segment.w, EA=segment.EA,
                        mode=boundary.mode, input_value=boundary.input_value,
                        config=config, mu=seabed.mu, MBL=segment.MBL,
                    )
                else:
                    # Touchdown em rampa
                    result = solve_sloped_seabed_single_segment(
                        L=segment.length, h=h_drop, w=segment.w, EA=segment.EA,
                        mode=boundary.mode, input_value=boundary.input_value,
                        mu=seabed.mu, slope_rad=slope, MBL=segment.MBL,
                        config=config,
                    )
            elif boundary.mode == SolutionMode.RANGE:
                X_crit = critical_range_for_touchdown(segment.length, h_drop)
                if boundary.input_value >= X_crit:
                    # Fully suspended em modo Range
                    result = solve_elastic_iterative(
                        L=segment.length, h=h_drop, w=segment.w, EA=segment.EA,
                        mode=boundary.mode, input_value=boundary.input_value,
                        config=config, mu=seabed.mu, MBL=segment.MBL,
                    )
                else:
                    # Touchdown em rampa, modo Range
                    result = solve_sloped_seabed_single_segment(
                        L=segment.length, h=h_drop, w=segment.w, EA=segment.EA,
                        mode=boundary.mode, input_value=boundary.input_value,
                        mu=seabed.mu, slope_rad=slope, MBL=segment.MBL,
                        config=config,
                    )
            else:
                raise ValueError(f"modo inválido: {boundary.mode}")
        elif h_drop <= 1e-6:
            # Caso degenerado: fairlead e âncora no mesmo nível (ambos no fundo).
            # Sem catenária — linha horizontal no seabed, só atrito + elasticidade.
            result = solve_laid_line(
                L=segment.length,
                w=segment.w,
                EA=segment.EA,
                mode=boundary.mode,
                input_value=boundary.input_value,
                mu=seabed.mu,
                MBL=segment.MBL,
                config=config,
            )
        else:
            result = solve_elastic_iterative(
                L=segment.length,
                h=h_drop,
                w=segment.w,
                EA=segment.EA,
                mode=boundary.mode,
                input_value=boundary.input_value,
                config=config,
                mu=seabed.mu,
                MBL=segment.MBL,
            )
    except ValueError as exc:
        # Erros físicos previsíveis — incrementamos com sugestões concretas
        # de correção (em vez de só "INVALID_CASE: <texto técnico>").
        friendly = _friendly_invalid_message(str(exc), segment, boundary)
        return SolverResult(
            status=ConvergenceStatus.INVALID_CASE,
            message=friendly,
            water_depth=boundary.h,
            startpoint_depth=boundary.startpoint_depth,
            solver_version=SOLVER_VERSION,
        )
    except Exception as exc:  # noqa: BLE001
        # Erros numéricos (overflow, div/0) caem aqui.
        return SolverResult(
            status=ConvergenceStatus.NUMERICAL_ERROR,
            message=(
                f"Erro numérico interno do solver: {exc}. "
                "Tente alterar levemente os parâmetros (ex.: ±1 % no T_fl ou L)."
            ),
            water_depth=boundary.h,
            startpoint_depth=boundary.startpoint_depth,
            solver_version=SOLVER_VERSION,
        )

    # Anexa os parâmetros geométricos globais + versão do solver para o plot
    # reconstruir o sistema de coordenadas surface-relative (superfície em
    # y=0, seabed em y=-water_depth, fairlead em y=-startpoint_depth).
    #
    # Batimetria nos dois pontos: anchor está no seabed sob a sua coluna
    # d'água (depth_at_anchor = boundary.h por convenção). Sob o fairlead,
    # a profundidade do seabed é deslocada por tan(slope)·X_total —
    # quando slope > 0 (sobe ao fairlead), depth_at_fairlead < depth_at_anchor.
    depth_at_fairlead = boundary.h - math.tan(seabed.slope_rad) * result.total_horz_distance

    # F5.4.6b — Anchor uplift severity. Drag anchors (DA / VLA) toleram
    # pouco ângulo de uplift; convencional ≤ 5° "ok", 5°–15° "warning",
    # > 15° "critical". Pilars e suction caissons toleram mais — usuário
    # pode considerar warnings como aceitáveis quando souber o tipo.
    uplift_deg = abs(math.degrees(result.angle_wrt_horz_anchor))
    if uplift_deg <= 5.0:
        uplift_severity = "ok"
    elif uplift_deg <= 15.0:
        uplift_severity = "warning"
    else:
        uplift_severity = "critical"

    result = result.model_copy(update={
        "water_depth": boundary.h,
        "startpoint_depth": boundary.startpoint_depth,
        "solver_version": SOLVER_VERSION,
        "depth_at_anchor": boundary.h,
        "depth_at_fairlead": depth_at_fairlead,
        "anchor_uplift_severity": uplift_severity,
    })

    # Pós-classificação (Camada 7 + alert_level da Seção 5 Documento A).
    if result.status == ConvergenceStatus.CONVERGED:
        try:
            alert = classify_utilization(
                result.utilization, criteria_profile, user_limits,
            )
        except ValueError as exc:
            # Configuração inválida do perfil (ex.: USER_DEFINED sem user_limits).
            return SolverResult(
                **{
                    **result.model_dump(),
                    "status": ConvergenceStatus.INVALID_CASE,
                    "message": f"Perfil de critério mal configurado: {exc}",
                }
            )

        # Check 1: linha rompida (utilization >= broken_ratio do perfil ativo).
        # Matemáticamente converge, mas é engenheiramente inválido.
        if alert == AlertLevel.BROKEN:
            return SolverResult(
                **{
                    **result.model_dump(),
                    "status": ConvergenceStatus.INVALID_CASE,
                    "alert_level": AlertLevel.BROKEN,
                    "message": (
                        f"Linha rompida: T_fl/MBL = {result.utilization:.2f} "
                        f"(perfil {criteria_profile.value}, broken_ratio="
                        f"{_broken_ratio(criteria_profile, user_limits):.2f}). "
                        "Caso fisicamente inviável. "
                        "Verifique comprimento, geometria ou tipo de linha."
                    ),
                }
            )

        # Check 2: ill-conditioned (linha muito taut, sensibilidade extrema).
        L_stretched = result.stretched_length
        X = result.total_horz_distance
        h = boundary.h
        L_taut = math.sqrt(X * X + h * h)
        taut_margin = L_stretched / L_taut if L_taut > 0 else float("inf")
        if 1.0 < taut_margin < 1.0001:
            return SolverResult(
                **{
                    **result.model_dump(),
                    "status": ConvergenceStatus.ILL_CONDITIONED,
                    "alert_level": alert,
                    "message": (
                        f"Convergiu mas caso mal condicionado: linha a "
                        f"{(taut_margin - 1) * 100:.3f}% do taut, alta sensibilidade. "
                        "Resultado deve ser usado com cautela. "
                        f"({result.message})"
                    ),
                }
            )

        # Caso normal convergido: injeta alert_level.
        return SolverResult(
            **{**result.model_dump(), "alert_level": alert}
        )

    return result


def _friendly_invalid_message(
    raw: str, segment: LineSegment, boundary: BoundaryConditions,
) -> str:
    """
    Converte uma mensagem técnica do solver em uma mensagem prática para o
    engenheiro, com sugestão de correção concreta sempre que possível.

    Cobre os erros mais comuns que aparecem na prática:
      - T_fl ≤ w·h  → linha não sustenta a coluna d'água
      - L ≤ √(X² + h²) (rígido)  → linha mais curta que a distância taut
      - L ≤ h (modo Tension)  → linha mais curta que a lâmina
      - Strain > 5%  → input em unidade errada
      - X < L (modo Range, laid line)  → X menor que o cabo
      - "linha rompida" (T_fl ≥ MBL)  → MBL excedido

    Para erros não reconhecidos, devolve o original prefixado com "Caso
    inviável:".
    """
    h = boundary.h
    L = segment.length
    w = segment.w
    MBL = segment.MBL
    raw_lower = raw.lower()

    # Heurística 1: T_fl insuficiente para sustentar coluna d'água
    if "insuficiente para sustentar" in raw_lower or "t_fl=" in raw_lower and "w·h" in raw:
        wh = w * h
        return (
            f"T_fl insuficiente: a tração no fairlead não sustenta o peso "
            f"da coluna d'água até o fairlead (w·h ≈ {wh / 1000:.1f} kN). "
            "Aumente T_fl, reduza a lâmina d'água, ou use um cabo mais leve."
        )

    # Heurística 2: comprimento curto para a distância pedida
    if "linha mais curta que a lâmina" in raw_lower or "fairlead inalcançável" in raw_lower:
        return (
            f"Linha curta demais: o comprimento ({L:.0f} m) é menor ou igual "
            f"à lâmina d'água ({h:.0f} m). "
            "Aumente o comprimento da linha para pelo menos h + margem."
        )

    # Heurística 3: X >= X_max (modo Range, geometria impossível sem elasticidade)
    if "x_max" in raw_lower or "linha rígida" in raw_lower or "não alcança" in raw_lower:
        return (
            "Distância horizontal X excede o máximo geométrico √(L² − h²). "
            "A linha precisaria esticar mais do que o EA permite. "
            "Reduza X (ou aumente o comprimento da linha)."
        )

    # Heurística 4: strain implausível → unidade errada
    if "strain final" in raw_lower or "implaus" in raw_lower:
        return (
            f"{raw}\n"
            f"Verificações sugeridas: w deve estar em N/m (não kgf/m), "
            f"EA em N (não te). Se você importou de um .moor antigo, "
            "use o seletor de unidades para conferir os valores."
        )

    # Heurística 5: rompimento (utilization > broken_ratio)
    if "linha rompida" in raw_lower or "broken_ratio" in raw_lower:
        return (
            f"{raw} O fairlead está sob T = {boundary.input_value / 1000:.1f} kN, "
            f"acima do MBL ({MBL / 1000:.1f} kN). "
            "Reduza T_fl, troque por um cabo de MBL maior ou alivie a geometria."
        )

    # Heurística 6: X < L em laid line
    if "x" in raw_lower and "compactar" in raw_lower:
        return (
            f"X ({boundary.input_value:.0f} m) menor que o comprimento da linha "
            f"({L:.0f} m): isso exigiria compressão axial, fisicamente impossível. "
            "Aumente X ou reduza L."
        )

    # Fallback: prepend "Caso inviável:" sem repetir se já vier
    if raw_lower.startswith("caso"):
        return raw
    return f"Caso inviável: {raw}"


__all__ = ["solve"]
