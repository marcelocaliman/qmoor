"""
Testes das restrições de contorno suportadas pelo solver.

Cobre:
- Âncora elevada do seabed (endpoint_grounded=False) → INVALID_CASE.
- Fairlead submerso (startpoint_depth ∈ (0, h)) → CONVERGED com drop reduzido.
- Fairlead no seabed (startpoint_depth == h) → CONVERGED via laid_line.
- Fairlead abaixo do seabed (startpoint_depth > h) → INVALID_CASE.
- Multi-segmento (len(line_segments) > 1) → INVALID_CASE.
"""
from __future__ import annotations

from backend.solver.solver import solve
from backend.solver.types import (
    BoundaryConditions,
    ConvergenceStatus,
    LineSegment,
    SeabedConfig,
    SolutionMode,
)


LBF_FT_TO_N_M = 14.593903


def _seg_padrao() -> LineSegment:
    return LineSegment(
        length=450.0, w=13.78 * LBF_FT_TO_N_M, EA=34.25e6, MBL=3.78e6,
    )


# ==============================================================================
# Âncora elevada — ainda não suportada
# ==============================================================================


def test_endpoint_grounded_false_retorna_invalid_case() -> None:
    """Âncora elevada do seabed exige modelagem distinta (pendente)."""
    bc = BoundaryConditions(
        h=300, mode=SolutionMode.TENSION, input_value=785_000,
        endpoint_grounded=False,
    )
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "endpoint_grounded" in r.message or "elevada" in r.message.lower()


# ==============================================================================
# Fairlead submerso — suportado desde que drop efetivo > 0
# ==============================================================================


def test_startpoint_depth_submerso_converge() -> None:
    """
    Fairlead submerso reduz o drop efetivo. Para drop de 200 m
    (h=300, startpoint_depth=100) com a mesma T_fl, a geometria
    acomoda mais linha no seabed → total_grounded_length > 0.
    """
    bc = BoundaryConditions(
        h=300, mode=SolutionMode.TENSION, input_value=785_000,
        startpoint_depth=100.0,
    )
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.CONVERGED
    # Campos geométricos globais devem ser propagados para o resultado
    assert r.water_depth == 300.0
    assert r.startpoint_depth == 100.0
    # endpoint_depth aqui vem do solver interno, que opera com drop=200
    assert abs(r.endpoint_depth - 200.0) < 1e-3


def test_fairlead_no_seabed_dispatches_para_laid_line() -> None:
    """
    Fairlead no mesmo nível da âncora: linha 100% horizontal no seabed.
    Tração varia linearmente por atrito, sem catenária.
    """
    seabed = SeabedConfig(mu=0.6)
    bc = BoundaryConditions(
        h=300, mode=SolutionMode.TENSION, input_value=600_000,
        startpoint_depth=300.0,
    )
    r = solve([_seg_padrao()], bc, seabed=seabed)
    assert r.status == ConvergenceStatus.CONVERGED
    # No caso horizontal não há trecho suspenso
    assert r.total_suspended_length == 0.0
    assert r.total_grounded_length > 0.0
    # Queda de tração = atrito total μ·w·L
    seg = _seg_padrao()
    expected_drop = 0.6 * seg.w * seg.length
    assert abs((r.fairlead_tension - r.anchor_tension) - expected_drop) < 1.0
    # Coords_y devem estar todas no seabed (drop=0 → y=0 no frame do solver)
    assert max(abs(y) for y in r.coords_y) < 1e-6


def test_fairlead_abaixo_do_seabed_invalid_case() -> None:
    """startpoint_depth > h: fairlead "enterrado" é fisicamente impossível."""
    bc = BoundaryConditions(
        h=300, mode=SolutionMode.TENSION, input_value=785_000,
        startpoint_depth=350.0,
    )
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.INVALID_CASE
    assert "startpoint_depth" in r.message or "inviável" in r.message.lower()


def test_default_endpoint_grounded_e_startpoint_depth() -> None:
    """Defaults preservados: endpoint_grounded=True, startpoint_depth=0."""
    bc = BoundaryConditions(h=300, mode=SolutionMode.TENSION, input_value=785_000)
    assert bc.endpoint_grounded is True
    assert bc.startpoint_depth == 0.0
    r = solve([_seg_padrao()], bc)
    assert r.status == ConvergenceStatus.CONVERGED
    assert r.water_depth == 300.0
    assert r.startpoint_depth == 0.0


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
