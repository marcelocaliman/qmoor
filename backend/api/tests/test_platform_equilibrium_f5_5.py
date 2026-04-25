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


# ──────────────────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────────────────


def _create_via_api(client) -> int:  # type: ignore[no-untyped-def]
    """Helper: cria spread 4× via POST e devolve o id."""
    payload = _spread_4x().model_dump()
    resp = client.post("/api/v1/mooring-systems", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


def test_post_equilibrium_carga_zero(client) -> None:  # type: ignore[no-untyped-def]
    msys_id = _create_via_api(client)
    resp = client.post(
        f"/api/v1/mooring-systems/{msys_id}/equilibrium",
        json={"Fx": 0.0, "Fy": 0.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["converged"] is True
    assert body["offset_magnitude"] < 1e-3
    assert body["n_converged"] == 4


def test_post_equilibrium_com_carga(client) -> None:  # type: ignore[no-untyped-def]
    msys_id = _create_via_api(client)
    resp = client.post(
        f"/api/v1/mooring-systems/{msys_id}/equilibrium",
        json={"Fx": 30_000.0, "Fy": 0.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["converged"] is True
    assert body["offset_xy"][0] > 0  # +X
    assert abs(body["offset_xy"][1]) < 0.5  # ~0 em Y
    # Resíduo dentro da tolerância
    assert body["residual_magnitude"] < 10.0


def test_post_equilibrium_id_inexistente_retorna_404(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/mooring-systems/9999/equilibrium",
        json={"Fx": 1000.0},
    )
    assert resp.status_code == 404


def test_post_equilibrium_preview(client) -> None:  # type: ignore[no-untyped-def]
    """Endpoint de preview — recebe input completo + env, sem persistir."""
    payload = {
        "system": _spread_4x().model_dump(),
        "env": {"Fx": 25_000.0, "Fy": 15_000.0},
    }
    resp = client.post(
        "/api/v1/mooring-systems/equilibrium-preview", json=payload,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["converged"] is True
    # Componente +X e +Y no offset (mesmo sentido da carga)
    assert body["offset_xy"][0] > 0
    assert body["offset_xy"][1] > 0


# ──────────────────────────────────────────────────────────────────────
# F5.6 — Watchcircle
# ──────────────────────────────────────────────────────────────────────


def test_watchcircle_solver_simetrico() -> None:
    """Spread 4× simétrico + carga rotacionada → envelope ~circular,
    cada offset com magnitude similar."""
    from backend.solver.equilibrium import compute_watchcircle
    msys = _spread_4x()
    res = compute_watchcircle(msys, magnitude_n=30_000.0, n_steps=12)
    assert len(res.points) == 12
    assert res.n_failed == 0
    assert res.max_offset_magnitude > 0

    # Em spread simétrico, a magnitude do offset varia pouco entre
    # azimuths (~10% no máximo, dependendo de não-linearidades).
    mags = [p.equilibrium.offset_magnitude for p in res.points]
    rel_var = (max(mags) - min(mags)) / max(mags)
    assert rel_var < 0.15, (
        f"Variação relativa do offset {rel_var:.2%} muito alta para "
        "spread simétrico"
    )


def test_watchcircle_offset_segue_carga() -> None:
    """A direção do offset deve casar com a direção da carga."""
    from backend.solver.equilibrium import compute_watchcircle
    msys = _spread_4x()
    res = compute_watchcircle(msys, magnitude_n=20_000.0, n_steps=8)
    for p in res.points:
        eq = p.equilibrium
        if eq.offset_magnitude < 0.05:
            continue  # offset muito pequeno, direção não confiável
        diff = abs(eq.offset_azimuth_deg - p.azimuth_deg)
        diff = min(diff, 360.0 - diff)
        assert diff < 10.0, (
            f"Azimuth do offset {eq.offset_azimuth_deg:.1f}° != "
            f"azimuth da carga {p.azimuth_deg:.1f}° (diff {diff:.1f}°)"
        )


def test_watchcircle_carga_zero() -> None:
    """Magnitude zero → todos os offsets ≈ 0."""
    from backend.solver.equilibrium import compute_watchcircle
    msys = _spread_4x()
    res = compute_watchcircle(msys, magnitude_n=0.0, n_steps=12)
    assert len(res.points) == 12
    assert res.max_offset_magnitude < 1e-3


def test_watchcircle_n_steps_invalido_lanca() -> None:
    from backend.solver.equilibrium import compute_watchcircle
    msys = _spread_4x()
    with pytest.raises(ValueError, match="n_steps"):
        compute_watchcircle(msys, magnitude_n=10_000.0, n_steps=2)


def test_post_watchcircle_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    msys_id = _create_via_api(client)
    resp = client.post(
        f"/api/v1/mooring-systems/{msys_id}/watchcircle",
        json={"magnitude_n": 25_000.0, "n_steps": 12},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_steps"] == 12
    assert len(body["points"]) == 12
    assert body["n_failed"] == 0
    assert body["max_offset_magnitude"] > 0


def test_post_watchcircle_id_inexistente(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(
        "/api/v1/mooring-systems/9999/watchcircle",
        json={"magnitude_n": 1000.0, "n_steps": 8},
    )
    assert resp.status_code == 404
