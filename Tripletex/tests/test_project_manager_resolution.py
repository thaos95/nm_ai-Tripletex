import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def project_manager_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v2/customer":
            return httpx.Response(200, json={"values": [{"id": 2001, "name": "Rio Azul Lda"}]})

        if request.method == "GET" and request.url.path == "/v2/employee":
            if request.url.params.get("email") == "goncalo.oliveira@example.org":
                return httpx.Response(
                    200,
                    json={
                        "values": [
                            {
                                "id": 1001,
                                "firstName": "Goncalo",
                                "lastName": "Oliveira",
                                "email": "goncalo.oliveira@example.org",
                                "employments": [],
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "id": 1002,
                            "firstName": "Fallback",
                            "lastName": "Manager",
                            "email": "fallback@example.org",
                            "employments": [{"id": 1}],
                        }
                    ]
                },
            )

        if request.method == "POST" and request.url.path == "/v2/project":
            payload = json.loads(request.content.decode("utf-8"))
            recorded.setdefault("project_payloads", []).append(payload)
            return httpx.Response(200, json={"value": {"id": 4001}})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_solve_create_project_uses_fallback_manager_before_first_post() -> None:
    recorded: dict = {}
    app.dependency_overrides[get_client_transport] = lambda: project_manager_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": 'Crie o projeto "Implementacao Rio" vinculado ao cliente Rio Azul Lda (org. no 827937223). O gerente de projeto e Goncalo Oliveira (goncalo.oliveira@example.org).',
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert len(recorded["project_payloads"]) == 1
    assert recorded["project_payloads"][0]["projectManager"]["id"] == 1002
    app.dependency_overrides.clear()
