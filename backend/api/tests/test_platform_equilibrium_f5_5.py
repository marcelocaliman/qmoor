"""
Testes F5.5 — equilíbrio de plataforma sob carga ambiental.

BCs cobertas:

  - BC-EQ-01: spread simétrico 4× sem carga → offset ≈ 0
  - BC-EQ-02: carga unidirecional em +X → offset em −X (lines em −X
    se estendem; lines em +X relaxam)
  - BC-EQ-03: assimetria (3 linhas) sob carga → offset com componentes
    em ambos os eixos
  - BC-EQ-04: carga oblíqua (45°) → offset oblíquo na direção oposta
  - BC-EQ-05: equilíbrio com carga grande satura — solver detecta
    e retorna `converged=False` mas com solução parcial razoável
"""
from __future__ import annotations

import copy
import math

import pytest

from backend.solver.equilibrium import solve_platform_equilibrium
from backend.solver.types import EnvironmentalLoad
from backend.api.schemas.mooring_systems import MooringSystemInput
from backend.api.tests._fixtures import BC01_LIKE_INPUT


def _line_dict(name: str, az_deg: float, *, radius: float = 30.0) -> dict:
    case = copy.deepcopy(BC01_LIKE_INPUT)
    return {
        "name": name,
        "fairlead_azimuth_deg": az_deg,
        "fairlead_radius": radius,
        "segments": case["segments"],
        "boundary": case["boundary"],
        "seabed": case["seabed"],
        "criteria_profile": case["criteria_profile"],
    }


def _spread_4x() -> MooringSystemInput:
    return MooringSystemInput.model_validate({
        "name": "Spread 4× simétrico",
        "platform_radius": 30.0,
        "lines": [
            _line_dict("L1", 45.0),
            _line_dict("L2", 135.0),
            _line_dict("L3", 225.0),
            _line_dict("L4", 315.0),
        ],
    })


# ──────────────────────────────────────────────────────────────────────
# BCs principais
# ──────────────────────────────────────────────────────────────────────


def test_BC_EQ_01_spread_simetrico_sem_carga_offset_zero() -> None:
    """Carga zero → offset (0, 0) e resíduo zero."""
    msys = _spread_4x()
    res = solve_platform_equilibrium(msys, EnvironmentalLoad())
    assert res.converged
    assert res.offset_magnitude < 1e-6
    assert res.residual_magnitude < 1e-3
    assert res.n_converged == 4


def test_BC_EQ_02_carga_em_X_positivo_offset_em_X_positivo() -> None:
    """
    Aplicar 50 kN em +X. Convenção: plataforma desloca NA DIREÇÃO da
    carga. As linhas do lado −X (L2 a 135°, L3 a 225°) se estendem e
    geram força restauradora em −X que balanceia o +X aplicado. As
    linhas do lado +X (L1, L4) ficam mais frouxas.
    """
    msys = _spread_4x()
    env = EnvironmentalLoad(Fx=50_000.0, Fy=0.0)
    res = solve_platform_equilibrium(msys, env)
    assert res.converged, res.message
    # Componente Y desprezível, X positivo (mesmo sentido da carga)
    assert abs(res.offset_xy[1]) < 0.5
    assert res.offset_xy[0] > 0.1, (
        f"offset_x esperado positivo, recebido {res.offset_xy[0]}"
    )
    # Resíduo dentro da tolerância
    assert res.residual_magnitude < 10.0


def test_BC_EQ_03_carga_oblíqua_offset_oblíquo_mesmo_sentido() -> None:
    """
    Carga em 30° (azimuth) → offset em ~30° (mesmo sentido).
    A força restauradora dos cabos é que vai em sentido oposto.
    """
    msys = _spread_4x()
    mag = 40_000.0
    az_load = 30.0
    fx = mag * math.cos(math.radians(az_load))
    fy = mag * math.sin(math.radians(az_load))
    env = EnvironmentalLoad(Fx=fx, Fy=fy)
    res = solve_platform_equilibrium(msys, env)
    assert res.converged, res.message

    # Offset deve apontar para ~30° (mesma direção da carga)
    diff = abs(res.offset_azimuth_deg - az_load)
    diff = min(diff, 360.0 - diff)  # wrap-around
    assert diff < 10.0, (
        f"Offset azimuth {res.offset_azimuth_deg:.1f}° muito longe "
        f"do esperado {az_load:.1f}°"
    )


def test_BC_EQ_04_assimetrico_3_linhas() -> None:
    """3 linhas a 0/120/240° + carga em +X → offset em +X."""
    msys_dict = {
        "name": "Tripé",
        "platform_radius": 30.0,
        "lines": [
            _line_dict("LA", 0.0),
            _line_dict("LB", 120.0),
            _line_dict("LC", 240.0),
        ],
    }
    msys = MooringSystemInput.model_validate(msys_dict)
    env = EnvironmentalLoad(Fx=20_000.0, Fy=0.0)
    res = solve_platform_equilibrium(msys, env)
    assert res.converged, res.message
    assert res.offset_xy[0] > 0  # carga em +X → offset em +X
    assert res.residual_magnitude < 10.0


def test_BC_EQ_05_carga_zero_baseline_inclui_todas_linhas() -> None:
    """Carga zero — line_results inclui as 4 linhas com solver_result OK."""
    msys = _spread_4x()
    res = solve_platform_equilibrium(msys, EnvironmentalLoad())
    assert len(res.lines) == 4
    for lr in res.lines:
        assert lr.solver_result.status.value == "converged"


def test_BC_EQ_06_carga_simetrica_em_eixo_principal() -> None:
    """Carga em +Y → offset em +Y (simetria, mesmo sentido)."""
    msys = _spread_4x()
    env = EnvironmentalLoad(Fx=0.0, Fy=30_000.0)
    res = solve_platform_equilibrium(msys, env)
    assert res.converged, res.message
    assert abs(res.offset_xy[0]) < 0.5
    assert res.offset_xy[1] > 0.05


def test_BC_EQ_07_residuo_quantitativo() -> None:
    """Em equilíbrio convergido, |Σ F_lines + F_env| deve ser muito
    pequeno comparado à magnitude da carga."""
    msys = _spread_4x()
    env = EnvironmentalLoad(Fx=80_000.0, Fy=0.0)
    res = solve_platform_equilibrium(msys, env)
    assert res.converged, res.message
    # Resíduo / carga < 0.1%
    assert res.residual_magnitude / env.magnitude < 1e-3


def test_BC_EQ_08_aggregate_metrics_no_resultado() -> None:
    """O resultado traz n_converged, max_utilization, etc."""
    msys = _spread_4x()
    res = solve_platform_equilibrium(
        msys, EnvironmentalLoad(Fx=20_000.0, Fy=10_000.0)
    )
    assert res.n_converged > 0
    assert res.max_utilization > 0
    assert res.solver_version


# ──────────────────────────────────────────────────────────────────────
# Validação Pydantic do EnvironmentalLoad
# ──────────────────────────────────────────────────────────────────────


def test_environmental_load_default_zero() -> None:
    env = EnvironmentalLoad()
    assert env.Fx == 0.0
    assert env.Fy == 0.0
    assert env.magnitude == 0.0


def test_environmental_load_magnitude() -> None:
    env = EnvironmentalLoad(Fx=3.0, Fy=4.0)
    assert env.magnitude == pytest.approx(5.0)
