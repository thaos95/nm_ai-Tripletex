import pytest
from pydantic import ValidationError

from app.schemas import FilePayload, SolveRequest, TripletexCredentials


def test_file_payload_rejects_empty_strings() -> None:
    with pytest.raises(ValidationError):
        FilePayload(filename=" ", mime_type="text/plain", content_base64="YWJj")


def test_tripletex_credentials_reject_non_https() -> None:
    with pytest.raises(ValidationError):
        TripletexCredentials(base_url="http://tx-proxy.ainm.no/v2", session_token="token")


def test_solve_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        SolveRequest(
            prompt=" ",
            files=[],
            tripletex_credentials={"base_url": "https://tx-proxy.ainm.no/v2", "session_token": "token"},
        )

