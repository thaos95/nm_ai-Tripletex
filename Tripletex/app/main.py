import httpx
from typing import Dict, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.attachments.service import decode_files, describe_attachments, extract_attachment_text
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.logging_utils import get_logger
from app.parser import parse_prompt
from app.planner import build_plan
from app.schemas import SolveRequest, SolveResponse, TaskType
from app.workflows.executor import execute_plan

logger = get_logger()
app = FastAPI(title="Tripletex Agent", version="0.1.0")


def require_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    if not settings.api_key:
        return
    expected = f"Bearer {settings.api_key}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_tripletex_client(
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport] = None,
) -> TripletexClient:
    return TripletexClient(
        base_url=str(request.tripletex_credentials.base_url),
        session_token=request.tripletex_credentials.session_token,
        verify_tls=settings.verify_tls,
        transport=transport,
    )


def get_client_transport() -> Optional[httpx.BaseTransport]:
    return None


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/solve", response_model=SolveResponse, dependencies=[Depends(require_api_key)])
def solve(
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport] = Depends(get_client_transport),
) -> SolveResponse:
    decoded_files = decode_files(request.files)
    attachment_text = extract_attachment_text(decoded_files)
    attachment_description = describe_attachments(decoded_files)
    parsing_input = request.prompt
    if attachment_description:
        parsing_input = "{0}\n\nAttachment metadata:\n{1}".format(parsing_input, attachment_description)
    if attachment_text:
        parsing_input = "{0}\n\nAttachment text:\n{1}".format(parsing_input, attachment_text)

    parsed_task = parse_prompt(parsing_input)
    plan = build_plan(parsed_task)

    logger.info(
        "solve_start task_type=%s language=%s attachments=%s prompt=%r parsed_fields=%r match_fields=%r related=%r",
        parsed_task.task_type,
        parsed_task.language_hint,
        len(decoded_files),
        request.prompt[:500],
        parsed_task.fields,
        parsed_task.match_fields,
        parsed_task.related_entities,
    )

    if parsed_task.task_type == TaskType.UNSUPPORTED:
        return SolveResponse()

    client = get_tripletex_client(request, transport)
    try:
        result = execute_plan(client, plan)
    except TripletexClientError as exc:
        logger.exception("solve_failed task_type=%s prompt=%r", parsed_task.task_type, request.prompt[:500])
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        client.close()

    logger.info(
        "solve_completed task_type=%s operations=%s",
        result.task_type,
        len(result.operations),
    )
    return SolveResponse()
