import httpx
from fastapi.testclient import TestClient

from app.main import app, get_client_transport
from app.parser import parse_prompt
from app.schemas import TaskType
from app.validator import validate_and_normalize_task

from tests.test_app import recording_transport


def test_parse_employee_hidden_prompt_keeps_birth_and_start_dates() -> None:
    parsed = parse_prompt(
        "Me har ein ny tilsett som heiter Geir Stolsvik, fodd 6. March 1990. Opprett vedkomande som tilsett med e-post geir.stlsvik@example.org og startdato 14. November 2026."
    )
    validated = validate_and_normalize_task(parsed)
    assert validated.parsed_task.task_type == TaskType.CREATE_EMPLOYEE
    assert validated.parsed_task.fields["birthDate"] == "1990-03-06"
    assert validated.parsed_task.fields["startDate"] == "2026-11-14"


def test_solve_create_employee_omits_proxy_invalid_start_date_field() -> None:
    recorded: dict = {}
    app.dependency_overrides[get_client_transport] = lambda: recording_transport(recorded)
    client = TestClient(app)
    response = client.post(
        "/solve",
        json={
            "prompt": "Me har ein ny tilsett som heiter Geir Stolsvik, fodd 6. March 1990. Opprett vedkomande som tilsett med e-post geir.stlsvik@example.org og startdato 14. November 2026.",
            "files": [],
            "tripletex_credentials": {"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        },
    )
    assert response.status_code == 200
    assert recorded["employee_payload"]["dateOfBirth"] == "1990-03-06"
    assert "dateFrom" not in recorded["employee_payload"]
    app.dependency_overrides.clear()
