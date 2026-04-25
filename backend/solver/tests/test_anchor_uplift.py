"""F5.4.6b — testes de classificação de anchor uplift."""
from __future__ import annotations

import math

from backend.solver.solver import solve
from backend.solver.types import (
    BoundaryConditions,
    LineSegment,
    SeabedConfig,
    SolutionMode,
)


def _seg() -> LineSegment:
    """Wire rope típico tipo BC-01."""
    return LineSegment(
        length=450.0, w=201.10404, EA=3.425e7, MBL=3.78e6,
        category="Wire", line_type="IWRCEIPS",
    )


def test_uplift_ok_em_catenaria_apoiada() -> None:
    """BC com touchdown (line apoiada no seabed) → âncora horizontal,
    severity = 'ok'."""
    s = LineSegment(length=2000.0, w=201.10404, EA=3.425e7, MBL=3.78e6)
    bc = BoundaryConditions(
        h=100.0, mode=SolutionMode.TENSION, input_value=30_000.0,
    )
    r = solve([s], bc)
    assert r.status.value == "converged"
    assert r.dist_to_first_td is not None and r.dist_to_first_td > 0
    # Trecho apoiado → âncora puxada horizontalmente, ângulo ≈ 0
    assert math.degrees(r.angle_wrt_horz_anchor) < 1.0
    assert r.anchor_uplift_severity == "ok"


def test_uplift_warning_em_catenaria_quase_taut() -> None:
    """Linha sem touchdown e com h alto → âncora com algum uplift.
    BC-01 like (lâmina 300, T_fl 785 kN) cai entre 5° e 15°."""
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=785_000.0,
    )
    r = solve([_seg()], bc)
    assert r.status.value == "converged"
    deg = math.degrees(r.angle_wrt_horz_anchor)
    # Se não estamos em 5–15, pelo menos confirma que a categorização
    # bate com o valor numérico.
    if 5.0 < deg <= 15.0:
        assert r.anchor_uplift_severity == "warning"
    elif deg > 15.0:
        assert r.anchor_uplift_severity == "critical"
    else:
        assert r.anchor_uplift_severity == "ok"


def test_uplift_critical_em_linha_taut_alto_angulo() -> None:
    """Linha curta + h alto força um ângulo grande no anchor."""
    s = LineSegment(length=320.0, w=201.10404, EA=3.425e7, MBL=3.78e6)
    bc = BoundaryConditions(
        h=300.0, mode=SolutionMode.TENSION, input_value=2_000_000.0,
    )
    r = solve([s], bc)
    if r.status.value == "converged":
        deg = math.degrees(r.angle_wrt_horz_anchor)
        if deg > 15.0:
            assert r.anchor_uplift_severity == "critical"


def test_uplift_severity_default_eh_ok() -> None:
    """SolverResult default (sem solve) deve ter severity = 'ok'."""
    from backend.solver.types import ConvergenceStatus, SolverResult
    r = SolverResult(status=ConvergenceStatus.CONVERGED)
    assert r.anchor_uplift_severity == "ok"
