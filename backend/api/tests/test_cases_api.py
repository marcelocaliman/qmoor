"""Testes dos endpoints de casos (F2.3)."""
from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from backend.api.tests._fixtures import BC01_LIKE_INPUT


# ==============================================================================
# POST /cases — criar
# ==============================================================================


def test_criar_caso_201(client: TestClient) -> None:
    resp = client.post("/api/v1/cases", json=BC01_LIKE_INPUT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["name"] == BC01_LIKE_INPUT["name"]
    assert body["input"]["boundary"]["h"] == 300.0
    assert body["latest_executions"] == []
    assert "created_at" in body and "updated_at" in body


def test_criar_caso_com_multi_segmento_422(client: TestClient) -> None:
    """MVP v1 rejeita 2+ segmentos pelo schema (max_length=1)."""
    payload = deepcopy(BC01_LIKE_INPUT)
    payload["segments"].append(payload["segments"][0])
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "validation_error"


def test_criar_caso_sem_name_422(client: TestClient) -> None:
    payload = deepcopy(BC01_LIKE_INPUT)
    del payload["name"]
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 422


def test_criar_caso_length_negativo_422(client: TestClient) -> None:
    payload = deepcopy(BC01_LIKE_INPUT)
    payload["segments"][0]["length"] = -10.0
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 422


def test_criar_caso_mode_invalido_422(client: TestClient) -> None:
    payload = deepcopy(BC01_LIKE_INPUT)
    payload["boundary"]["mode"] = "Parabolic"  # não existe
    resp = client.post("/api/v1/cases", json=payload)
    assert resp.status_code == 422


# ==============================================================================
# GET /cases/{id}
# ==============================================================================


def test_get_case_200(client: TestClient) -> None:
    created = client.post("/api/v1/cases", json=BC01_LIKE_INPUT).json()
    resp = client.get(f"/api/v1/cases/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == created["id"]
    # Input é round-trip: dump → load → re-dump deve bater nos campos chave
    assert body["input"]["boundary"]["input_value"] == 785000.0
    assert body["input"]["segments"][0]["length"] == 450.0


def test_get_case_404(client: TestClient) -> None:
    resp = client.get("/api/v1/cases/99999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "case_not_found"
    assert "99999" in body["error"]["message"]


# ==============================================================================
# PUT /cases/{id}
# ==============================================================================


def test_update_case_200(client: TestClient) -> None:
    created = client.post("/api/v1/cases", json=BC01_LIKE_INPUT).json()
    updated_payload = deepcopy(BC01_LIKE_INPUT)
    updated_payload["name"] = "BC-01 editado"
    updated_payload["description"] = "descrição alterada"
    updated_payload["boundary"]["input_value"] = 800000.0
    resp = client.put(f"/api/v1/cases/{created['id']}", json=updated_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "BC-01 editado"
    assert body["input"]["boundary"]["input_value"] == 800000.0
    # updated_at > created_at
    assert body["updated_at"] >= body["created_at"]


def test_update_case_404(client: TestClient) -> None:
    resp = client.put("/api/v1/cases/99999", json=BC01_LIKE_INPUT)
    assert resp.status_code == 404


def test_update_case_422_para_payload_invalido(client: TestClient) -> None:
    created = client.post("/api/v1/cases", json=BC01_LIKE_INPUT).json()
    payload = deepcopy(BC01_LIKE_INPUT)
    payload["segments"][0]["EA"] = 0  # violada validator do solver
    resp = client.put(f"/api/v1/cases/{created['id']}", json=payload)
    assert resp.status_code == 422


# ==============================================================================
# DELETE /cases/{id}
# ==============================================================================


def test_delete_case_200(client: TestClient) -> None:
    created = client.post("/api/v1/cases", json=BC01_LIKE_INPUT).json()
    resp = client.delete(f"/api/v1/cases/{created['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"
    # Segundo DELETE deve dar 404
    resp2 = client.delete(f"/api/v1/cases/{created['id']}")
    assert resp2.status_code == 404


def test_delete_case_404(client: TestClient) -> None:
    resp = client.delete("/api/v1/cases/99999")
    assert resp.status_code == 404


# ==============================================================================
# GET /cases (lista, paginação, search)
# ==============================================================================


def test_list_cases_vazio(client: TestClient) -> None:
    resp = client.get("/api/v1/cases")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_list_cases_paginacao(client: TestClient) -> None:
    # Cria 5 casos
    for i in range(5):
        payload = deepcopy(BC01_LIKE_INPUT)
        payload["name"] = f"Case {i}"
        client.post("/api/v1/cases", json=payload)
    resp = client.get("/api/v1/cases?page=1&page_size=2")
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    # Página 3 deve ter o restante (5 - 2*2 = 1)
    resp3 = client.get("/api/v1/cases?page=3&page_size=2")
    body3 = resp3.json()
    assert len(body3["items"]) == 1


def test_list_cases_search(client: TestClient) -> None:
    for name in ["Taut wire", "Slack chain", "Taut polyester"]:
        payload = deepcopy(BC01_LIKE_INPUT)
        payload["name"] = name
        client.post("/api/v1/cases", json=payload)
    resp = client.get("/api/v1/cases?search=taut")
    body = resp.json()
    assert body["total"] == 2
    assert all("taut" in item["name"].lower() for item in body["items"])


def test_list_cases_pagesize_invalido_422(client: TestClient) -> None:
    resp = client.get("/api/v1/cases?page_size=999")
    assert resp.status_code == 422
