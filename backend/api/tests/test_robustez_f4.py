"""
Testes da F4.5 — robustez backend.

Cobertura:
  - Rate limit ativo: > 100 req/min em uma rota recebe HTTP 429.
  - Mensagens patológicas: T_fl < w·h devolve mensagem com sugestão.
  - solver_version presente em todo SolverResult retornado pela API.
  - Logging estruturado escreve no arquivo rotativo configurado.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import logging_config
from backend.api.tests._fixtures import BC01_LIKE_INPUT


# ==============================================================================
# solver_version no SolverResult
# ==============================================================================


def test_preview_devolve_solver_version(client: TestClient) -> None:
    resp = client.post("/api/v1/solve/preview", json=BC01_LIKE_INPUT)
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("solver_version", "") != ""


def test_preview_invalido_tambem_devolve_solver_version(
    client: TestClient,
) -> None:
    payload = deepcopy(BC01_LIKE_INPUT)
    payload["boundary"]["input_value"] = 1.0
    resp = client.post("/api/v1/solve/preview", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    raw = body.get("error") or body.get("detail")
    detail = raw.get("detail") if isinstance(raw, dict) else None
    assert detail is not None
    assert detail.get("solver_version", "") != ""


# ==============================================================================
# Mensagens patológicas amigáveis
# ==============================================================================


def test_t_fl_baixo_devolve_mensagem_com_sugestao(client: TestClient) -> None:
    """T_fl < w·h: solver deve sugerir aumentar T_fl ou reduzir lâmina."""
    payload = deepcopy(BC01_LIKE_INPUT)
    # w·h ≈ 60 kN; T_fl=10 kN é claramente insuficiente
    payload["boundary"]["input_value"] = 10_000.0
    resp = client.post("/api/v1/solve/preview", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    raw = body.get("error") or body.get("detail")
    msg = (raw.get("message") if isinstance(raw, dict) else "") or ""
    assert "T_fl" in msg or "tração" in msg.lower()
    assert "aumente" in msg.lower() or "reduza" in msg.lower()


# ==============================================================================
# Rate limit
# ==============================================================================


def test_rate_limit_dispara_apos_100_req_minuto(client: TestClient) -> None:
    """
    Limite default 100/minute: enviamos 105 e esperamos pelo menos uma 429.
    Usamos /api/v1/health (rota leve, não toca DB) para o teste ser rápido
    e não acumular dados em outras tabelas.
    """
    last_status: int | None = None
    for _ in range(105):
        resp = client.get("/api/v1/health")
        last_status = resp.status_code
        if resp.status_code == 429:
            break
    assert last_status == 429, (
        f"esperava 429 após 100 req/min, último status: {last_status}"
    )


# ==============================================================================
# Logging estruturado
# ==============================================================================


def test_log_arquivo_rotativo_existe(tmp_path: Path, monkeypatch) -> None:
    """
    Reconfigurar logging com DB_PATH apontando para tmp e gerar uma linha
    deve escrever em logs/qmoor.log.
    """
    # Reset interno do flag idempotente para forçar reconfiguração no diretório novo.
    monkeypatch.setattr(logging_config, "_CONFIGURED", False)
    monkeypatch.setattr(
        "backend.api.logging_config.DB_PATH", str(tmp_path / "qmoor.db"),
    )
    logging_config.configure_logging()

    log_file = tmp_path / "logs" / "qmoor.log"
    logging_config.log_solver_execution(
        case_id=42, status="converged", iterations=14, elapsed_ms=33.0,
        alert_level="ok", message="Catenária elástica convergida.",
    )
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "case_id=42" in content
    assert "status=converged" in content
    assert "iterations=14" in content
