"""
Testes F5.4.2 — solver dispatcher + agregação + endpoints.

Estrutura:
  1. Solver puro (`solve_mooring_system`):
     - BC-MS-LINE-01: spread simétrico 4× → resultante ≈ 0
     - BC-MS-LINE-02: spread assimétrico (2 linhas a 0° e 90°) → resultante
       em direção esperada
     - BC-MS-LINE-03: linha inválida no meio → entra no resultado mas
       fica de fora do agregado de forças (n_invalid > 0)
     - Posições de fairlead/anchor batem com fórmula radial.
  2. Service (`solve_and_persist`):
     - Persiste execução; respeita retenção de 10.
  3. API:
     - POST /mooring-systems/{id}/solve cria execução e retorna result.
     - POST /mooring-systems/preview-solve resolve sem persistir.
     - GET /mooring-systems/{id} traz `latest_executions` populado.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from backend.api.db.models import MooringSystemExecutionRecord
from backend.api.schemas.mooring_systems import MooringSystemInput
from backend.api.services.mooring_system_service import (
    EXECUTION_RETENTION,
    create_mooring_system,
    solve_and_persist,
)
from backend.solver.multi_line import solve_mooring_system
from backend.solver.types import AlertLevel, ConvergenceStatus
from backend.api.tests._fixtures import BC01_LIKE_INPUT


# ──────────────────────────────────────────────────────────────────────
# Builders
# ──────────────────────────────────────────────────────────────────────


def _line_dict(name: str, az_deg: float, *, radius: float = 30.0) -> dict:
    """Linha BC-01 like na posição polar dada."""
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


def _symmetric_spread_4x() -> MooringSystemInput:
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


def _asymmetric_2x() -> MooringSystemInput:
    """Duas linhas a 0° e 90° → resultante deve apontar pra ~45°."""
    return MooringSystemInput.model_validate({
        "name": "Asymm 2x",
        "platform_radius": 30.0,
        "lines": [
            _line_dict("Lx", 0.0),
            _line_dict("Ly", 90.0),
        ],
    })


def _spread_with_invalid_line() -> MooringSystemInput:
    """3 linhas válidas + 1 inválida (T_fl absurda → solver falha)."""
    bad = _line_dict("Lbroken", 90.0)
    # Tração impossível: maior que MBL · 1000 (forçar invalid_case ou broken).
    bad["boundary"] = {**bad["boundary"], "input_value": 1e15}
    return MooringSystemInput.model_validate({
        "name": "Mixed",
        "platform_radius": 30.0,
        "lines": [
            _line_dict("L_a", 0.0),
            bad,
            _line_dict("L_b", 180.0),
            _line_dict("L_c", 270.0),
        ],
    })


# ──────────────────────────────────────────────────────────────────────
# 1. Solver puro
# ──────────────────────────────────────────────────────────────────────


def test_bc_ms_line_01_spread_simetrico_resultante_aprox_zero() -> None:
    """4 linhas idênticas em 45/135/225/315° → Σ F_i ≈ 0."""
    msys = _symmetric_spread_4x()
    res = solve_mooring_system(msys)

    assert res.n_converged == 4
    assert res.n_invalid == 0
    assert len(res.lines) == 4

    # Cada linha contribui com força |H| pra fora; soma vetorial cancela.
    h_per_line = res.lines[0].solver_result.H
    assert h_per_line > 0
    # Tolerância relativa: 1% da magnitude individual basta.
    assert res.aggregate_force_magnitude < 0.01 * h_per_line, (
        f"Resultante {res.aggregate_force_magnitude:.2f} N não é "
        f"desprezível vs H_individual={h_per_line:.2f} N"
    )


def test_bc_ms_line_02_assimetrico_aponta_para_bissetriz() -> None:
    """2 linhas iguais a 0° e 90° → resultante a ~45°, magnitude H·√2."""
    msys = _asymmetric_2x()
    res = solve_mooring_system(msys)

    assert res.n_converged == 2
    h = res.lines[0].solver_result.H
    expected_mag = h * math.sqrt(2.0)
    assert abs(res.aggregate_force_magnitude - expected_mag) / expected_mag < 1e-3
    # Azimuth ~ 45° (bissetriz das duas direções)
    assert abs(res.aggregate_force_azimuth_deg - 45.0) < 0.5


def test_bc_ms_line_03_linha_invalida_fica_fora_do_agregado() -> None:
    """Linha que falha no solver não entra no agregado (n_invalid > 0)."""
    msys = _spread_with_invalid_line()
    res = solve_mooring_system(msys)

    # Pelo menos a linha "Lbroken" não converge.
    assert res.n_invalid >= 1
    assert res.n_converged == len(msys.lines) - res.n_invalid

    # As outras 3 linhas estão em 0/180/270°. Resultante simétrico em
    # 0° + 180° = 0; sobra a contribuição de 270° → resultante negativa em y.
    fy = res.aggregate_force_xy[1]
    fx = res.aggregate_force_xy[0]
    assert abs(fx) < 1.0  # 0+180 cancelam
    assert fy < 0.0  # contribuição da L_c em 270° aponta pra -y


def test_posicao_fairlead_e_anchor_batem_com_formula_radial() -> None:
    """fairlead_xy = R·(cos θ, sin θ); anchor_xy = (R+X)·(cos θ, sin θ)."""
    msys = _symmetric_spread_4x()
    res = solve_mooring_system(msys)

    for line_res in res.lines:
        theta = math.radians(line_res.fairlead_azimuth_deg)
        r = line_res.fairlead_radius
        # Fairlead
        assert abs(line_res.fairlead_xy[0] - r * math.cos(theta)) < 1e-6
        assert abs(line_res.fairlead_xy[1] - r * math.sin(theta)) < 1e-6
        # Anchor: (R + X) na mesma direção radial
        x_total = line_res.solver_result.total_horz_distance
        assert abs(line_res.anchor_xy[0] - (r + x_total) * math.cos(theta)) < 1e-6
        assert abs(line_res.anchor_xy[1] - (r + x_total) * math.sin(theta)) < 1e-6


def test_worst_alert_level_segue_hierarquia() -> None:
    """Quando todas as linhas estão `ok`, worst_alert_level == OK."""
    msys = _symmetric_spread_4x()
    res = solve_mooring_system(msys)
    # BC-01 like: T/MBL = 785/3780 ≈ 0.21 → alert_level = OK.
    assert res.worst_alert_level == AlertLevel.OK


def test_solver_version_propagado_no_resultado() -> None:
    msys = _symmetric_spread_4x()
    res = solve_mooring_system(msys)
    assert res.solver_version  # non-empty
    # Cada linha individual também carrega solver_version no SolverResult.
    for lr in res.lines:
        assert lr.solver_result.solver_version


# ──────────────────────────────────────────────────────────────────────
# 2. Service: solve_and_persist
# ──────────────────────────────────────────────────────────────────────


def test_solve_and_persist_cria_execucao(tmp_db: Path) -> None:
    from backend.api.db import session as ds
    msys = _symmetric_spread_4x()
    with ds.SessionLocal() as db:
        rec = create_mooring_system(db, msys)
        out = solve_and_persist(db, rec.id)
        assert out is not None
        sys_rec, exec_rec = out
        assert sys_rec.id == rec.id
        assert exec_rec.mooring_system_id == rec.id
        assert exec_rec.n_converged == 4
        assert exec_rec.n_invalid == 0
        # Desnormalização preenchida
        assert exec_rec.aggregate_force_magnitude is not None
        assert exec_rec.worst_alert_level in {a.value for a in AlertLevel}


def test_solve_and_persist_sistema_inexistente_retorna_none(tmp_db: Path) -> None:
    from backend.api.db import session as ds
    with ds.SessionLocal() as db:
        assert solve_and_persist(db, 99999) is None


def test_retencao_mantem_apenas_10_execucoes(tmp_db: Path) -> None:
    from backend.api.db import session as ds
    msys = _symmetric_spread_4x()
    with ds.SessionLocal() as db:
        rec = create_mooring_system(db, msys)
        # Roda solve 12 vezes
        for _ in range(EXECUTION_RETENTION + 2):
            out = solve_and_persist(db, rec.id)
            assert out is not None
        # Conta execuções restantes
        n = (
            db.query(MooringSystemExecutionRecord)
            .filter_by(mooring_system_id=rec.id)
            .count()
        )
        assert n == EXECUTION_RETENTION


# ──────────────────────────────────────────────────────────────────────
# 3. API endpoints
# ──────────────────────────────────────────────────────────────────────


def test_post_create_retorna_201_e_id(client) -> None:  # type: ignore[no-untyped-def]
    msys = _symmetric_spread_4x().model_dump()
    resp = client.post("/api/v1/mooring-systems", json=msys)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] > 0
    assert body["input"]["name"] == "Spread 4× simétrico"
    assert body["latest_executions"] == []


def test_post_solve_retorna_execution_e_persiste(client) -> None:  # type: ignore[no-untyped-def]
    msys = _symmetric_spread_4x().model_dump()
    create = client.post("/api/v1/mooring-systems", json=msys).json()
    msys_id = create["id"]

    solve = client.post(f"/api/v1/mooring-systems/{msys_id}/solve")
    assert solve.status_code == 200, solve.text
    body = solve.json()
    assert body["mooring_system_id"] == msys_id
    assert body["result"]["n_converged"] == 4
    assert len(body["result"]["lines"]) == 4

    # Detail vê a execução em latest_executions
    detail = client.get(f"/api/v1/mooring-systems/{msys_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["latest_executions"]) == 1
    assert body["latest_executions"][0]["id"] == solve.json()["id"]


def test_solve_id_inexistente_retorna_404(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.post("/api/v1/mooring-systems/9999/solve")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "mooring_system_not_found"


def test_preview_solve_nao_persiste(client) -> None:  # type: ignore[no-untyped-def]
    msys = _symmetric_spread_4x().model_dump()
    # Cria pra termos algo na lista
    client.post("/api/v1/mooring-systems", json=msys)

    resp = client.post("/api/v1/mooring-systems/preview-solve", json=msys)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_converged"] == 4
    assert "lines" in body and len(body["lines"]) == 4

    # A lista em /mooring-systems mostra zero execuções desnormalizadas
    # (a UI vai chamar GET detail pra ver isso, mas confirmamos que o
    # preview NÃO aumentou o histórico nem disparou execução).
    listing = client.get("/api/v1/mooring-systems").json()
    assert listing["total"] == 1
    detail = client.get(f"/api/v1/mooring-systems/{listing['items'][0]['id']}").json()
    assert detail["latest_executions"] == []


def test_put_substitui_config_e_recalcula_line_count(client) -> None:  # type: ignore[no-untyped-def]
    msys = _symmetric_spread_4x().model_dump()
    create = client.post("/api/v1/mooring-systems", json=msys).json()
    msys_id = create["id"]

    new_msys = _asymmetric_2x().model_dump()
    resp = client.put(f"/api/v1/mooring-systems/{msys_id}", json=new_msys)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["input"]["lines"]) == 2
    assert body["input"]["name"] == "Asymm 2x"


def test_delete_remove_sistema_e_executions(client) -> None:  # type: ignore[no-untyped-def]
    msys = _symmetric_spread_4x().model_dump()
    create = client.post("/api/v1/mooring-systems", json=msys).json()
    msys_id = create["id"]
    # Roda solve pra ter execução
    client.post(f"/api/v1/mooring-systems/{msys_id}/solve")

    resp = client.delete(f"/api/v1/mooring-systems/{msys_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Idempotente: segunda chamada → 404
    assert client.delete(f"/api/v1/mooring-systems/{msys_id}").status_code == 404


def test_export_json_retorna_payload_e_attachment_header(client) -> None:  # type: ignore[no-untyped-def]
    """GET /export/json retorna o output completo + Content-Disposition."""
    msys = _symmetric_spread_4x().model_dump()
    create = client.post("/api/v1/mooring-systems", json=msys).json()
    msys_id = create["id"]
    client.post(f"/api/v1/mooring-systems/{msys_id}/solve")

    resp = client.get(f"/api/v1/mooring-systems/{msys_id}/export/json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == msys_id
    assert body["input"]["name"] == "Spread 4× simétrico"
    assert len(body["latest_executions"]) == 1

    cd = resp.headers.get("content-disposition")
    assert cd is not None and cd.startswith("attachment;")
    assert ".json" in cd


def test_export_json_id_inexistente_retorna_404(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/mooring-systems/9999/export/json")
    assert resp.status_code == 404


def test_export_pdf_sem_execucao_retorna_pdf_parcial(client) -> None:  # type: ignore[no-untyped-def]
    """PDF é gerado mesmo quando o sistema nunca foi resolvido."""
    msys = _symmetric_spread_4x().model_dump()
    create = client.post("/api/v1/mooring-systems", json=msys).json()
    msys_id = create["id"]

    resp = client.get(f"/api/v1/mooring-systems/{msys_id}/export/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    # PDF "magic header"
    assert resp.content.startswith(b"%PDF-")
    # Tem corpo razoável (>1 KB)
    assert len(resp.content) > 1024
    cd = resp.headers.get("content-disposition") or ""
    assert ".pdf" in cd


def test_export_pdf_com_execucao_inclui_resultados(client) -> None:  # type: ignore[no-untyped-def]
    """Após /solve, o PDF carrega o resultado completo."""
    msys = _symmetric_spread_4x().model_dump()
    create = client.post("/api/v1/mooring-systems", json=msys).json()
    msys_id = create["id"]
    client.post(f"/api/v1/mooring-systems/{msys_id}/solve")

    resp = client.get(f"/api/v1/mooring-systems/{msys_id}/export/pdf")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")
    # PDF com execução é maior (tabelas adicionais)
    assert len(resp.content) > 5000


def test_export_pdf_id_inexistente_retorna_404(client) -> None:  # type: ignore[no-untyped-def]
    resp = client.get("/api/v1/mooring-systems/9999/export/pdf")
    assert resp.status_code == 404
