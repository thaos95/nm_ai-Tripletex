import base64
import json

import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport


def travel_recording_transport(recorded: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v2/travelExpense":
            recorded["travel_expense_payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"value": {"id": 7001}})

        if request.method == "GET" and request.url.path == "/v2/employee":
            return httpx.Response(200, json={"values": [{"id": 1001, "firstName": "Svein", "lastName": "Berge"}]})

        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_attachment_text_can_route_vague_prompt_to_travel_expense() -> None:
    recorded = {}
    app.dependency_overrides[get_client_transport] = lambda: travel_recording_transport(recorded)
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": "Registrer dette.",
            "files": [
                {
                    "filename": "reise.txt",
                    "mime_type": "text/plain",
                    "content_base64": base64.b64encode(
                        'Reiseregning for Svein Berge (svein.berge@example.org). Reisa varte 5 dagar med diett (dagssats 800 kr). Utlegg: flybillett 2850 kr og taxi 200 kr.'.encode(
                            "utf-8"
                        )
                    ).decode("ascii"),
                }
            ],
            "tripletex_credentials": {
                "base_url": "https://tx-proxy.ainm.no/v2",
                "session_token": "token",
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {"status": "completed"}
    assert recorded["travel_expense_payload"]["amount"] == 7050.0
    app.dependency_overrides.clear()
