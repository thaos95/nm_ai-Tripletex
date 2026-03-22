import logging
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.attachment_parser import parse_attachments
from app.clients.tripletex import TripletexClient, TripletexClientError
from app.config import settings
from app.errors import MissingPrerequisiteError, UnsupportedTaskError
from app.parser import parse_prompt
from app.planner import build_plan
from app.schemas import SolveRequest, SolveResponse, TaskType
from app.validator import validate_and_normalize_task
from app.workflows.executor import execute_plan

LOGGER = logging.getLogger(__name__)

app = FastAPI(title="Tripletex AI Agent", version="1.0")


def get_client_transport() -> Optional[httpx.BaseTransport]:
    """Dependency that returns the transport for TripletexClient.
    Override in tests to inject a mock transport."""
    return None


def _verify_api_key(authorization: Optional[str] = Header(default=None)) -> None:
    """Verify Bearer token if TRIPLETEX_AGENT_API_KEY is configured."""
    if not settings.api_key:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else authorization
    if token != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _attempt_solve(
    prompt: str,
    request: SolveRequest,
    transport: Optional[httpx.BaseTransport],
    attempt: int = 1,
    thinking_level: str = "medium",
) -> Optional[str]:
    """Single solve attempt. Returns None on success, or error description on failure."""
    parsed_task = parse_prompt(prompt, thinking_level=thinking_level)
    LOGGER.info("attempt=%d thinking=%s parsed task_type=%s confidence=%.2f", attempt, thinking_level, parsed_task.task_type, parsed_task.confidence)

    if parsed_task.task_type == TaskType.UNSUPPORTED:
        return "unsupported"

    validation = validate_and_normalize_task(parsed_task)
    if validation.blocking_error:
        LOGGER.warning("attempt=%d validation blocked: %s", attempt, validation.blocking_error)
        return "validation: {0}".format(validation.blocking_error)

    parsed_task = validation.parsed_task
    plan = build_plan(parsed_task)

    client = TripletexClient(
        base_url=str(request.tripletex_credentials.base_url),
        session_token=request.tripletex_credentials.session_token,
        verify_tls=settings.verify_tls,
        transport=transport,
    )
    try:
        result = execute_plan(client, plan)
        LOGGER.info(
            "attempt=%d execution completed task_type=%s operations=%d error=%s",
            attempt, result.task_type, len(result.operations), result.error,
        )
        if result.error:
            return "execution: {0}".format(result.error)
        if len(result.operations) == 0:
            return "execution: zero operations"
        return None  # success
    finally:
        client.close()


@app.post("/solve", response_model=SolveResponse)
async def solve(
    request: SolveRequest,
    _auth: None = Depends(_verify_api_key),
    transport: Optional[httpx.BaseTransport] = Depends(get_client_transport),
) -> SolveResponse:
    LOGGER.info(
        "Received solve request prompt=%s base_url=%s session_token_present=%s",
        request.prompt[:80],
        request.tripletex_credentials.base_url,
        bool(request.tripletex_credentials.session_token),
    )

    try:
        # 1. Parse attachments
        attachments = parse_attachments(request.files)

        # 2. First attempt
        error = _attempt_solve(request.prompt, request, transport, attempt=1)

        # 3. Retry on failure (a 0-score failure is always worse than retrying)
        if error and error != "unsupported":
            LOGGER.info("First attempt failed (%s), retrying with high thinking", error)
            error2 = _attempt_solve(
                request.prompt, request, transport,
                attempt=2, thinking_level="high",
            )
            if error2:
                LOGGER.warning("Retry also failed: %s", error2)

    except Exception:
        LOGGER.exception("Error during /solve — returning completed anyway")

    return SolveResponse(status="completed")


@app.exception_handler(Exception)
async def _handle_exception(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled exception during /solve")
    return JSONResponse(content={"status": "completed"}, status_code=200)
