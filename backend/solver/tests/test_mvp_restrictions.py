"""
Testes das restrições explícitas do MVP v1 (A11 + A14 da auditoria).

Cobre:
- Âncora elevada do seabed (endpoint_grounded=False) → INVALID_CASE.
- Fairlead afundado (startpoint_depth>0) → INVALID_CASE.
- Multi-segmento (len(line_segments) > 1) → INVALID_CASE.
"""
from __future__ import annotations

from backend.solver.solver import solve
from backend.solver.types import (
    BoundaryConditions,
    ConvergenceStatus,
    LineSegment,
    SolutionMode,
)


LBF_FT_TO_N_M = 14.593903


def _seg_padrao() -> LineSegment:
    return LineSegment(
        length=450.0, w=13.78 * LBF_FT_TO_N_M, EA=34.25e6, MBL=3.78e6,
    )


# ==============================================================================
# A14 — Âncora elevada
# ==============================================================================


def test_endpoint_grounded_false_retorna_invalid_case() -> None:
    """MVP v1: âncora deve estar no seabed."""
    bc = BoundaryConditions(
        h=300, mode=SolutionMode.TENSION, input_value=785_000,
        endpoint_grounded=False,
    )
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "endpoint_grounded" in r.message or "elevada" in r.message.lower()
    # Mensagem deve indicar que é planejado para v2
    assert "v2" in r.message.lower()


def test_startpoint_depth_nonzero_retorna_invalid_case() -> None:
    """MVP v1: fairlead deve estar na superfície."""
    bc = BoundaryConditions(
        h=300, mode=SolutionMode.TENSION, input_value=785_000,
        startpoint_depth=10.0,
    )
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "startpoint_depth" in r.message or "fairlead" in r.message.lower()


def test_default_endpoint_grounded_e_startpoint_depth() -> None:
    """Defaults (True/0.0) mantêm comportamento pré-A14."""
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=785_000)
    assert bc.endpoint_grounded is True
    assert bc.startpoint_depth == 0.0
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.CONVERGED


# ==============================================================================
# A11 — Smoke test multi-segmento
# ==============================================================================


def test_multi_segmento_retorna_invalid_case() -> None:
    """
    v1 aceita UM segmento apenas (homogêneo). Fronteira documentada
    em Seção 9 do Documento A v2.2. Contrato verificável.
    """
    s1 = _seg_padrao()
    s2 = _seg_padrao()
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=785_000)
    r = solve([s1, s2], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "segmento" in r.message.lower() or "multi" in r.message.lower()
    assert "v2.1" in r.message


def test_lista_vazia_de_segmentos_retorna_invalid_case() -> None:
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=785_000)
    r = solve([], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "segmento" in r.message.lower()
