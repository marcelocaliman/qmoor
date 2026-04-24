"""
Camada 5/6 — Fachada pública do solver QMoor.

Unifica todas as camadas anteriores (catenária rígida, seabed no-friction,
atrito de Coulomb, correção elástica) em uma única função de entrada que
aceita as estruturas Pydantic de alto nível:

  solve(line_segments, boundary, seabed, config) -> SolverResult

Despacha para solve_elastic_iterative, que por sua vez usa o dispatch
rígido-suspenso vs touchdown em solve_rigid_suspended.

O MVP v1 suporta UMA linha homogênea (um LineSegment). Multi-segmento
fica para v2.1 conforme Seção 9 do Documento A v2.2.
"""
from __future__ import annotations

import math
from typing import Sequence

from .elastic import solve_elastic_iterative
from .types import (
    BoundaryConditions,
    ConvergenceStatus,
    LineSegment,
    SeabedConfig,
    SolutionMode,
    SolverConfig,
    SolverResult,
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
    if len(line_segments) > 1:
        # Decisão fechada: v2.1 terá multi-segmento. Seção 9 do Documento A.
        raise NotImplementedError(
            f"MVP v1 suporta apenas um segmento; {len(line_segments)} recebidos. "
            "Multi-segmento é escopo v2.1."
        )
    segment = line_segments[0]
    if segment.length <= 0 or segment.EA <= 0 or segment.MBL <= 0 or segment.w <= 0:
        raise ValueError("segmento com grandeza não-positiva (validado também por Pydantic)")
    if boundary.h <= 0:
        raise ValueError("lâmina d'água h deve ser > 0")
    if boundary.input_value <= 0:
        raise ValueError("input_value (T_fl ou X) deve ser > 0")
    if seabed.mu < 0:
        raise ValueError("coeficiente de atrito μ deve ser >= 0")
    # Validações específicas por modo (Seção 8 do MVP v2 PDF):
    if boundary.mode not in (SolutionMode.TENSION, SolutionMode.RANGE):
        raise ValueError(f"modo inválido: {boundary.mode}")
    return segment


def solve(
    line_segments: Sequence[LineSegment],
    boundary: BoundaryConditions,
    seabed: SeabedConfig | None = None,
    config: SolverConfig | None = None,
) -> SolverResult:
    """
    Executa o solver completo para uma linha isolada.

    Parâmetros
    ----------
    line_segments : lista com UM LineSegment (MVP v1 é homogêneo).
    boundary : condições de contorno (h, modo, input_value).
    seabed : configuração do seabed (μ, profundidade). Default μ=0.
    config : tolerâncias e max iter. Default SolverConfig().

    Retorna
    -------
    SolverResult — todos os campos da Seção 6 do MVP v2, incluindo
    status de convergência, geometria discretizada, tensões, comprimentos
    e ângulos.

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
        )

    try:
        result = solve_elastic_iterative(
            L=segment.length,
            h=boundary.h,
            w=segment.w,
            EA=segment.EA,
            mode=boundary.mode,
            input_value=boundary.input_value,
            config=config,
            mu=seabed.mu,
            MBL=segment.MBL,
        )
    except ValueError as exc:
        return SolverResult(
            status=ConvergenceStatus.INVALID_CASE,
            message=f"Caso inviável: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        # Erros numéricos (overflow, div/0) caem aqui.
        return SolverResult(
            status=ConvergenceStatus.NUMERICAL_ERROR,
            message=f"Erro numérico: {exc}",
        )

    # Pós-classificação (Camada 7): detecta casos ill-conditioned onde o
    # solver convergiu mas o resultado é sensível a pequenas variações.
    if result.status == ConvergenceStatus.CONVERGED:
        # Check 1: linha rompida (T_fl > MBL). Matemáticamente converge,
        # mas é um caso engenheiramente inválido (Seção 5 do Documento A).
        if result.utilization > 1.0:
            return SolverResult(
                **{
                    **result.model_dump(),
                    "status": ConvergenceStatus.INVALID_CASE,
                    "message": (
                        f"Linha rompida: T_fl/MBL = {result.utilization:.2f} > 1.0. "
                        "Caso fisicamente inviável. "
                        "Verifique comprimento, geometria ou tipo de linha."
                    ),
                }
            )

        L_stretched = result.stretched_length
        X = result.total_horz_distance
        h = boundary.h
        L_taut = math.sqrt(X * X + h * h)
        taut_margin = L_stretched / L_taut if L_taut > 0 else float("inf")
        # Linha dentro de 0,01% do taut → sensibilidade extrema.
        # Threshold conservador: casos operacionais normais frequentemente
        # ficam dentro de 0,1% ou 0,5% do taut sem serem mal-condicionados
        # em sentido estrito; apenas a aproximação MUITO apertada
        # (dT/dL → ∞ no limite exato) caracteriza ill_conditioned.
        if 1.0 < taut_margin < 1.0001:
            return SolverResult(
                **{
                    **result.model_dump(),
                    "status": ConvergenceStatus.ILL_CONDITIONED,
                    "message": (
                        f"Convergiu mas caso mal condicionado: linha a "
                        f"{(taut_margin - 1) * 100:.3f}% do taut, alta sensibilidade. "
                        "Resultado deve ser usado com cautela. "
                        f"({result.message})"
                    ),
                }
            )

    return result


__all__ = ["solve"]
