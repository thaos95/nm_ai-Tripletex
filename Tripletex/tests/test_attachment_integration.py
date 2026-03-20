import base64

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app, get_client_transport
from app.schemas import ParsedTask, SolveResponse, TaskType


def test_solve_passes_attachment_metadata_and_text_into_parser(monkeypatch) -> None:
    captured = {}

    def fake_parse_prompt(parsing_input: str) -> ParsedTask:
        captured["parsing_input"] = parsing_input
        return ParsedTask(task_type=TaskType.DELETE_TRAVEL_EXPENSE, confidence=1.0, fields={"travel_expense_id": 42})

    def fake_validate(parsed_task: ParsedTask):
        return type(
            "Validation",
            (),
            {
                "parsed_task": parsed_task,
                "warnings": [],
                "blocking_error": None,
                "safety": "safe",
            },
        )()

    def fake_execute_plan(client, plan):
        captured["parsed_task_type"] = plan.parsed_task.task_type
        return type("Result", (), {"task_type": plan.parsed_task.task_type, "operations": []})()

    monkeypatch.setattr(main_module, "parse_prompt", fake_parse_prompt)
    monkeypatch.setattr(main_module, "validate_and_normalize_task", fake_validate)
    monkeypatch.setattr(main_module, "execute_plan", fake_execute_plan)
    app.dependency_overrides[get_client_transport] = lambda: None
    client = TestClient(app)

    response = client.post(
        "/solve",
        json={
            "prompt": "Slett reiseregning 42",
            "files": [
                {
                    "filename": "invoice.txt",
                    "mime_type": "text/plain",
                    "content_base64": base64.b64encode("Beløp 450\nKunde Brattli AS".encode("utf-8")).decode("ascii"),
                }
            ],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )

    assert response.status_code == 200
    assert response.json() == SolveResponse().model_dump()
    assert "Attachment metadata:" in captured["parsing_input"]
    assert "filename=invoice.txt, mime_type=text/plain" in captured["parsing_input"]
    assert "Attachment text:" in captured["parsing_input"]
    assert "Beløp 450" in captured["parsing_input"]
    assert captured["parsed_task_type"] == TaskType.DELETE_TRAVEL_EXPENSE
    app.dependency_overrides.clear()
